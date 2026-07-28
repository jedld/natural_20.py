#!/usr/bin/env python3
"""Render a Natural20 map YAML to a tile-based PNG or JPEG image."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.map_image.batch import batch_render_missing_map_assets, find_maps_needing_assets
from natural20.map_image.renderer import render_map_image


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render Natural20 map YAML to tile-based PNG/JPEG images.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--campaign",
        help="Campaign directory (e.g. user_levels/outcasts_path)",
    )
    source.add_argument(
        "--input",
        help="Path to a standalone map YAML file",
    )

    parser.add_argument(
        "--batch-missing",
        action="store_true",
        help="Render background images for all maps with missing assets (requires --campaign)",
    )
    parser.add_argument(
        "--map",
        help="Map path or name within the campaign (e.g. maps/cathedral or cathedral)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output image path (.png or .jpg/.jpeg); not used with --batch-missing",
    )
    parser.add_argument(
        "--tile-size",
        type=int,
        default=None,
        help="Pixels per grid square (default: index.json tile_size or 64)",
    )
    parser.add_argument(
        "--palette",
        choices=["stone", "dirt", "grass", "cathedral", "sewer", "prison", "manor", "street", "cobble", "tavern", "docks"],
        default=None,
        help="Procedural palette (default: inferred from map name/description)",
    )
    parser.add_argument(
        "--layers",
        default=None,
        help="Comma-separated layers (default: base,objects,entities,meta; batch: base,objects)",
    )
    parser.add_argument(
        "--grid",
        action="store_true",
        help="Draw a faint tile grid overlay",
    )
    parser.add_argument(
        "--format",
        choices=["png", "jpeg", "jpg"],
        default=None,
        help="Output format (default: inferred from --output extension)",
    )
    parser.add_argument(
        "--diffusion",
        choices=["openai", "http", "stability", "sd", "mcp"],
        help="Optional diffusion provider for AI-generated background underlay (mcp = Image Gen MCP)",
    )
    parser.add_argument(
        "--diffusion-style",
        default="fantasy battlemap",
        help="Style phrase appended to the diffusion prompt",
    )
    parser.add_argument(
        "--diffusion-quality",
        choices=["auto", "high", "medium", "low"],
        default="medium",
        help="Quality preset for --diffusion mcp",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help="Image Gen MCP URL (default N20_IMAGE_GEN_MCP_URL or http://127.0.0.1:8020/mcp)",
    )
    parser.add_argument(
        "--prepare-textures",
        action="store_true",
        help="Generate MCP theme texture packs (floor/wall/water) before rendering",
    )
    parser.add_argument(
        "--force-textures",
        action="store_true",
        help="With --prepare-textures, overwrite existing texture packs",
    )
    parser.add_argument(
        "--background-opacity",
        type=float,
        default=0.55,
        help="Opacity for background/diffusion underlay (0-1, default: 0.55 so themed tiles stay visible)",
    )
    parser.add_argument(
        "--update-yaml",
        action="store_true",
        help="With --batch-missing, set background_image on map YAML after rendering",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --batch-missing, list maps that would be rendered without writing files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --batch-missing, re-render even when the asset already exists",
    )
    parser.add_argument(
        "--skip-unassigned",
        action="store_true",
        help="With --batch-missing, only fix maps that reference a missing background_image",
    )
    parser.add_argument(
        "--include-unlisted",
        action="store_true",
        help="With --batch-missing, also scan maps/*.yml not registered in game.yml",
    )
    parser.add_argument(
        "--skip-background",
        action="store_true",
        help="Do not composite map background_image (use when regenerating the asset itself)",
    )
    return parser


def _run_batch(args: argparse.Namespace) -> int:
    if not args.campaign:
        print("error: --batch-missing requires --campaign", file=sys.stderr)
        return 2

    layers = None
    if args.layers:
        layers = tuple(part.strip() for part in args.layers.split(",") if part.strip())

    if getattr(args, "prepare_textures", False):
        from natural20.map_image.gen_textures import ensure_theme_textures, themes_needed_for_campaign

        themes = themes_needed_for_campaign(Path(args.campaign))
        print(f"Preparing MCP textures for themes: {', '.join(themes)}")
        written = ensure_theme_textures(
            themes,
            mcp_url=args.mcp_url,
            force=bool(getattr(args, "force_textures", False)),
            quality=args.diffusion_quality,
        )
        print(f"Wrote {len(written)} texture atlas file(s)")

    if args.dry_run:
        jobs = find_maps_needing_assets(
            args.campaign,
            include_without_background=not args.skip_unassigned,
            include_unlisted=args.include_unlisted,
        )
        pending = [job for job in jobs if not job.asset_exists or args.force]
        if not pending:
            print("No missing map background assets found.")
            return 0
        print(f"Would render {len(pending)} map asset(s):")
        for job in pending:
            target = job.expected_asset_path
            print(f"  - {job.map_id}: {job.reason} -> {target}")
        return 0

    results = batch_render_missing_map_assets(
        args.campaign,
        tile_size=args.tile_size,
        palette=args.palette,
        layers=layers,
        show_grid=args.grid,
        diffusion=args.diffusion,
        diffusion_style=args.diffusion_style,
        diffusion_quality=args.diffusion_quality,
        mcp_url=args.mcp_url,
        background_opacity=args.background_opacity,
        update_yaml=args.update_yaml,
        dry_run=False,
        force=args.force,
        include_without_background=not args.skip_unassigned,
        include_unlisted=args.include_unlisted,
    )
    rendered = [result for result in results if not result.skipped]
    skipped = [result for result in results if result.skipped]
    for result in rendered:
        suffix = " (yaml updated)" if result.updated_yaml else ""
        print(f"Wrote {result.output_path} [{result.map_id}]{suffix}")
    for result in skipped:
        print(f"Skipped {result.map_id}: {result.message}")
    if not rendered and not skipped:
        print("No maps found.")
    elif not rendered:
        print("No missing map background assets to render.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.batch_missing:
        return _run_batch(args)

    if args.campaign and not args.map:
        parser.error("--map is required when using --campaign (or use --batch-missing)")
    if not args.output:
        parser.error("--output is required unless using --batch-missing")

    if getattr(args, "prepare_textures", False) and args.campaign:
        from natural20.map_image.gen_textures import ensure_theme_textures, themes_needed_for_campaign

        themes = themes_needed_for_campaign(Path(args.campaign))
        if args.palette:
            themes = [args.palette]
        written = ensure_theme_textures(
            themes,
            mcp_url=args.mcp_url,
            force=bool(getattr(args, "force_textures", False)),
            quality=args.diffusion_quality,
        )
        print(f"Wrote {len(written)} texture atlas file(s)")

    output = Path(args.output)
    image_format = args.format
    if image_format is None:
        suffix = output.suffix.lower().lstrip(".")
        image_format = "jpeg" if suffix in {"jpg", "jpeg"} else "png"

    layers = tuple(part.strip() for part in (args.layers or "base,objects,entities,meta").split(",") if part.strip())

    path = render_map_image(
        output=output,
        campaign=args.campaign,
        map_name=args.map,
        input_yaml=args.input,
        tile_size=args.tile_size or 64,
        palette=args.palette,
        layers=layers,
        show_grid=args.grid,
        image_format=image_format,
        diffusion=args.diffusion,
        diffusion_style=args.diffusion_style,
        diffusion_quality=args.diffusion_quality,
        mcp_url=args.mcp_url,
        background_opacity=args.background_opacity,
        skip_background_image=args.skip_background,
    )
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
