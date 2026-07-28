#!/usr/bin/env python3
"""Generate object spawner editor icons for non-wall fixtures in objects.yml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.image_gen.editor_asset_paths import (
    default_editor_output_dir,
    is_campaign_root,
    templates_editor_dir,
)
from natural20.image_gen.object_editor_icons import generate_object_editor_icons
from natural20.yaml_loader import load_campaign_yaml, templates_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate procedural editor icons for object spawner fixtures "
            "(terrain, traps, props, doors, etc.). Walls and door-walls use "
            "scripts/generate_wall_door_tile.py instead."
        )
    )
    parser.add_argument(
        "--root",
        default="templates",
        help="Session root: templates or user_levels/<campaign> (default: templates)",
    )
    parser.add_argument(
        "--campaign",
        default=None,
        help="Shorthand for --root user_levels/<slug> (overrides --root)",
    )
    parser.add_argument(
        "--yaml",
        default=None,
        help="objects.yml to read (default: derived from --root)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Force a single output directory (default: templates/assets/editor or "
            "per-object routing under campaign/assets/editor)"
        ),
    )
    parser.add_argument("--size", type=int, default=64, help="Icon size in pixels (default: 64)")
    parser.add_argument(
        "--palette",
        default="dirt",
        help="Map palette passed to procedural icon renderer (default: dirt)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing icons")
    return parser


def resolve_root(args: argparse.Namespace) -> Path:
    if args.campaign:
        return (REPO_ROOT / "user_levels" / args.campaign).resolve()
    root = Path(args.root)
    if not root.is_absolute():
        root = (REPO_ROOT / root).resolve()
    return root


def load_objects(root: Path, yaml_override: str | None) -> dict:
    if yaml_override:
        yaml_path = Path(yaml_override)
        if not yaml_path.is_absolute():
            yaml_path = (REPO_ROOT / yaml_path).resolve()
    elif is_campaign_root(root):
        yaml_path = root / "items" / "objects.yml"
        if yaml_path.is_file():
            return load_campaign_yaml(root, "objects")
        return {}
    else:
        yaml_path = templates_root() / "items" / "objects.yml"

    if not yaml_path.is_file():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")
    with yaml_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def main() -> int:
    args = build_parser().parse_args()
    root = resolve_root(args)
    try:
        objects = load_objects(root, args.yaml)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    campaign_root = root if is_campaign_root(root) else None
    if output_dir is None and not is_campaign_root(root):
        templates_editor_dir().mkdir(parents=True, exist_ok=True)

    results = generate_object_editor_icons(
        objects,
        output_dir=output_dir,
        campaign_root=campaign_root,
        size=args.size,
        palette=args.palette,
        force=args.force,
    )

    written = [row for row in results if row[2] == "written"]
    skipped = [row for row in results if row[2].startswith("skipped")]

    print(f"Processed objects from {root}")
    for object_id, output_path, status in results:
        if status == "written":
            print(f"✓ {output_path} ({object_id})")
        elif status.startswith("skipped"):
            print(f"✗ {object_id}: {status}")

    dest = output_dir or default_editor_output_dir(campaign_root)
    print(f"Generated {len(written)} icons")
    if output_dir is None:
        print("Icons routed to templates/assets/editor and/or campaign assets/editor")
    else:
        print(f"Output directory: {dest}")
    if skipped:
        print(f"Skipped {len(skipped)} objects with no procedural icon")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
