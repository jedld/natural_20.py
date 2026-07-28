#!/usr/bin/env python3
"""Scan for missing item, spell, and action icons and generate them via Image Gen MCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.image_gen.campaign_assets import status_probe
from natural20.image_gen.game_icons import (
    build_session,
    run_icon_generation,
    scan_missing_icons,
    default_item_output_dir,
    default_spell_output_dir,
    default_action_output_dir,
    default_effect_output_dir,
)
from natural20.image_gen.mcp_client import default_mcp_url
from natural20.image_gen.prompts import DEFAULT_ICON_STYLE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find missing item, spell, action, and effect icons, then generate them "
            "with the local Image Gen MCP server."
        )
    )
    parser.add_argument(
        "--root",
        default="templates",
        help="Session root to load item/spell YAML from (default: templates)",
    )
    parser.add_argument(
        "--campaign",
        default=None,
        help="Shorthand for --root user_levels/<slug> (overrides --root)",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help=f"Image Gen MCP endpoint (default: {default_mcp_url()})",
    )
    parser.add_argument(
        "--items",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include item icons from weapons/equipment/magic_items (default: on)",
    )
    parser.add_argument(
        "--item-objects",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Also scan map object interactables from items/objects.yml (default: off)",
    )
    parser.add_argument(
        "--item-packs",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Also scan equipment pack bundles from items/equipment_packs.yml (default: off)",
    )
    parser.add_argument(
        "--spells",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include spell icons from items/spells.yml (default: on)",
    )
    parser.add_argument(
        "--actions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include combat action bar icons from natural20/actions (default: on)",
    )
    parser.add_argument(
        "--effects",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include magical effect status icons from spells.yml (default: on)",
    )
    parser.add_argument(
        "--write-to",
        choices=("bundled", "campaign"),
        default="bundled",
        help="Where to write new item icons (spells always go to webapp/static/spells)",
    )
    parser.add_argument(
        "--item-output",
        default=None,
        help="Override item icon output directory",
    )
    parser.add_argument(
        "--spell-output",
        default=None,
        help="Override spell icon output directory",
    )
    parser.add_argument(
        "--action-output",
        default=None,
        help="Override action icon output directory (default: webapp/static/actions)",
    )
    parser.add_argument(
        "--effect-output",
        default=None,
        help="Override effect icon output directory (default: webapp/static/assets/effect)",
    )
    parser.add_argument(
        "--icon-style",
        default=DEFAULT_ICON_STYLE,
        help='Style phrase appended to every icon prompt (e.g. "flat style icons")',
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to item/spell id or image name (repeatable)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when the icon file already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned generations without calling the MCP",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Print missing icons as JSON and exit (no MCP calls)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate at most N missing icons (useful for smoke tests)",
    )
    parser.add_argument(
        "--item-size",
        type=int,
        default=128,
        help="Output item icon size in pixels (default: 128)",
    )
    parser.add_argument(
        "--spell-size",
        type=int,
        default=128,
        help="Output spell icon size in pixels (default: 128)",
    )
    parser.add_argument(
        "--action-size",
        type=int,
        default=128,
        help="Output action icon size in pixels (default: 128)",
    )
    parser.add_argument(
        "--effect-size",
        type=int,
        default=128,
        help="Output effect icon size in pixels (default: 128)",
    )
    parser.add_argument(
        "--optimize",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="PNG-optimize icons after generation (default: on)",
    )
    parser.add_argument(
        "--webp",
        action="store_true",
        help="Also write .webp companions next to generated PNG icons",
    )
    parser.add_argument(
        "--webp-quality",
        type=int,
        default=82,
        help="Quality for optional .webp companions (default: 82)",
    )
    parser.add_argument(
        "--quality",
        choices=("auto", "high", "medium", "low"),
        default="medium",
        help="Image Gen MCP quality preset",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional MCP model preset (qwen2512, flux-dev, flux-schnell)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Probe MCP readiness and exit",
    )
    return parser


def resolve_root(args: argparse.Namespace) -> Path:
    if args.campaign:
        return (REPO_ROOT / args.campaign).resolve()
    root = Path(args.root)
    if not root.is_absolute():
        root = (REPO_ROOT / root).resolve()
    return root


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = resolve_root(args)

    if args.status:
        probe = status_probe(args.mcp_url)
        print(json.dumps(probe, indent=2, default=str)[:4000])
        return 0 if probe.get("ok") else 1

    if not root.is_dir():
        print(f"Root not found: {root}", file=sys.stderr)
        return 2

    campaign_root = root if (root / "game.yml").is_file() or (root / "index.json").is_file() else None
    item_output = Path(args.item_output).resolve() if args.item_output else None
    spell_output = Path(args.spell_output).resolve() if args.spell_output else None
    if item_output is None:
        item_output = default_item_output_dir(campaign_root=campaign_root, write_to=args.write_to)
    if spell_output is None:
        spell_output = default_spell_output_dir()
    action_output = Path(args.action_output).resolve() if args.action_output else default_action_output_dir()
    effect_output = Path(args.effect_output).resolve() if args.effect_output else default_effect_output_dir()

    session = build_session(root)
    missing = scan_missing_icons(
        session,
        items=args.items,
        spells=args.spells,
        actions=args.actions,
        effects=args.effects,
        campaign_root=campaign_root,
        item_output_dir=item_output,
        spell_output_dir=spell_output,
        action_output_dir=action_output,
        effect_output_dir=effect_output,
        only=args.only or None,
        force=args.force,
        include_objects=args.item_objects,
        include_packs=args.item_packs,
    )

    if args.scan_only:
        payload = [
            {
                "kind": ref.kind,
                "id": ref.key,
                "label": ref.label,
                "image": ref.image_name,
                "output": str(ref.output_path),
                "source": ref.source,
            }
            for ref in missing
        ]
        print(json.dumps({"missing": len(payload), "icons": payload}, indent=2))
        return 0

    print(f"Missing icons: {len(missing)} (root={root})", flush=True)
    if not missing:
        return 0

    report = run_icon_generation(
        root=root,
        items=args.items,
        spells=args.spells,
        actions=args.actions,
        effects=args.effects,
        write_to=args.write_to,
        only=args.only or None,
        item_output_dir=item_output,
        spell_output_dir=spell_output,
        action_output_dir=action_output,
        effect_output_dir=effect_output,
        mcp_url=args.mcp_url,
        icon_style=args.icon_style,
        force=args.force,
        dry_run=args.dry_run,
        quality=args.quality,
        model=args.model,
        item_size=args.item_size,
        spell_size=args.spell_size,
        action_size=args.action_size,
        effect_size=args.effect_size,
        limit=args.limit,
        optimize=args.optimize,
        webp=args.webp,
        webp_quality=args.webp_quality,
        include_objects=args.item_objects,
        include_packs=args.item_packs,
    )

    for result in report.results:
        status = "ERROR" if result.error else ("SKIP" if result.skipped else "WRITE")
        detail = result.error or result.reason or str(result.output_path)
        print(f"[{status}] {result.kind}:{result.key} — {detail}", flush=True)

    print(
        f"Done. written={len(report.written)} skipped={sum(1 for r in report.results if r.skipped)} "
        f"errors={len(report.errors)}",
        flush=True,
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
