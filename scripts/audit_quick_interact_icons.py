#!/usr/bin/env python3
"""Audit object quick-interact icons and optionally generate missing assets via MCP."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.image_gen.game_icons import default_action_output_dir
from natural20.image_gen.mcp_client import ImageGenMcpClient, default_mcp_url, save_pil
from natural20.image_gen.prompts import action_icon_negative, action_icon_prompt
from natural20.image_gen.web_optimize import optimize_icon_for_web
from natural20.web.quick_interact_registry import (
    action_icon_dir,
    collect_quick_interact_icon_slugs,
    missing_quick_interact_icons,
)
from scripts.regenerate_quick_interact_icons import HOVER_ICON_SIZE, hover_icon_prompt, prepare_hover_icon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--objects-yml',
        action='append',
        default=[],
        help='Extra objects.yml paths to scan (repeatable)',
    )
    parser.add_argument(
        '--campaign-dir',
        action='append',
        default=[],
        help='Campaign root; scans items/objects.yml and maps/*.yml (repeatable)',
    )
    parser.add_argument(
        '--map-yml',
        action='append',
        default=[],
        help='Map YAML paths to scan for legend states/buttons (repeatable)',
    )
    parser.add_argument(
        '--generate-missing',
        action='store_true',
        help='Generate missing icons through Image Gen MCP',
    )
    parser.add_argument(
        '--mcp-url',
        default=None,
        help=f'Image Gen MCP endpoint (default: {default_mcp_url()})',
    )
    parser.add_argument(
        '--model',
        default='flux-dev',
        help='Image Gen MCP model preset (default: flux-dev)',
    )
    parser.add_argument(
        '--quality',
        default='medium',
        help='Generation quality preset',
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Output directory for generated icons',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List missing slugs only',
    )
    return parser


def _objects_yml_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    for campaign in args.campaign_dir:
        candidate = Path(campaign).resolve() / 'items' / 'objects.yml'
        if candidate.is_file():
            paths.append(candidate)
    for raw in args.objects_yml:
        path = Path(raw).resolve()
        if path.is_file():
            paths.append(path)
    return paths


def _map_yml_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    for campaign in args.campaign_dir:
        maps_dir = Path(campaign).resolve() / 'maps'
        if maps_dir.is_dir():
            paths.extend(sorted(maps_dir.glob('*.yml')))
    for raw in args.map_yml:
        path = Path(raw).resolve()
        if path.is_file():
            paths.append(path)
    return paths


def _prompt_for_ref(ref: dict[str, str]) -> str:
    action = ref['action']
    label = ref['label']
    return action_icon_prompt(slug=ref['slug'], label=label) + (
        f", {label} interaction for a fantasy object action button, "
        f"isolated symbol on solid pale gray background"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    extra_paths = _objects_yml_paths(args)
    map_paths = _map_yml_paths(args)
    missing = missing_quick_interact_icons(
        objects_yml_paths=extra_paths or None,
        map_yml_paths=map_paths or None,
    )

    print(f'Action icon directory: {action_icon_dir()}')
    print(
        'Known quick-interact slugs: '
        f"{len(collect_quick_interact_icon_slugs(objects_yml_paths=extra_paths or None, map_yml_paths=map_paths or None))}"
    )
    print(f'Missing icons: {len(missing)}')
    for ref in missing:
        print(f"  - {ref['slug']} ({ref['action']}: {ref['label']})")

    if args.dry_run or not args.generate_missing:
        return 0 if not missing else 1

    if not missing:
        return 0

    out_dir = Path(args.output).resolve() if args.output else default_action_output_dir()
    client = ImageGenMcpClient(args.mcp_url or default_mcp_url())
    client.initialize()
    try:
        for ref in missing:
            slug = ref['slug']
            out_path = out_dir / f'{slug}.png'
            prompt = _prompt_for_ref(ref)
            print(f'Generating {slug} -> {out_path}', flush=True)
            generated = client.generate_image(
                prompt=prompt,
                size='512x512',
                quality=args.quality,
                negative_prompt=action_icon_negative(slug=slug),
                output_format='png',
                model=args.model,
            )
            icon = prepare_hover_icon(generated.image, size=HOVER_ICON_SIZE)
            out_dir.mkdir(parents=True, exist_ok=True)
            save_pil(icon, out_path, format='PNG')
            optimize_icon_for_web(out_path, max_dim=HOVER_ICON_SIZE)
    finally:
        client.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
