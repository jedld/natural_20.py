#!/usr/bin/env python3
"""Regenerate small transparent hover icons for door/chest quick interactions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.image_gen.game_icons import default_action_output_dir, prepare_square_icon
from natural20.image_gen.mcp_client import ImageGenMcpClient, default_mcp_url, save_pil
from natural20.image_gen.prompts import action_icon_negative, action_icon_prompt
from natural20.image_gen.web_optimize import optimize_icon_for_web
from PIL import Image

QUICK_INTERACT_SLUGS = (
    "interact_open",
    "interact_close",
    "interact_lock",
    "interact_unlock",
    "open_chest",
    "closed_chest",
)

HOVER_ICON_SIZE = 75
BG_TOLERANCE = 32


def remove_flat_background(image: Image.Image, *, tolerance: int = BG_TOLERANCE) -> Image.Image:
    """Turn a flat single-color backdrop into alpha for small UI overlays."""
    rgba = image.convert("RGBA")
    w, h = rgba.size
    corners = [
        rgba.getpixel((0, 0))[:3],
        rgba.getpixel((w - 1, 0))[:3],
        rgba.getpixel((0, h - 1))[:3],
        rgba.getpixel((w - 1, h - 1))[:3],
    ]
    bg = tuple(sum(channel[i] for channel in corners) // len(corners) for i in range(3))
    pixels = []
    for r, g, b, _a in rgba.getdata():
        if (
            abs(r - bg[0]) <= tolerance
            and abs(g - bg[1]) <= tolerance
            and abs(b - bg[2]) <= tolerance
        ):
            pixels.append((r, g, b, 0))
        else:
            pixels.append((r, g, b, 255))
    rgba.putdata(pixels)
    return rgba


def prepare_hover_icon(image: Image.Image, size: int = HOVER_ICON_SIZE) -> Image.Image:
    square = prepare_square_icon(image, 512)
    transparent = remove_flat_background(square)
    if transparent.size != (size, size):
        transparent = transparent.resize((size, size), Image.Resampling.LANCZOS)
    return transparent


def hover_icon_prompt(slug: str) -> str:
    label = slug.replace("_", " ").title()
    return action_icon_prompt(slug=slug, label=label) + ", isolated symbol on solid pale gray background"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mcp-url",
        default=None,
        help=f"Image Gen MCP endpoint (default: {default_mcp_url()})",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: webapp/static/actions)",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=HOVER_ICON_SIZE,
        help=f"Final icon size in pixels (default: {HOVER_ICON_SIZE})",
    )
    parser.add_argument(
        "--model",
        default="flux-dev",
        help="Image Gen MCP model preset (default: flux-dev)",
    )
    parser.add_argument(
        "--quality",
        default="medium",
        help="Generation quality preset",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to slug (repeatable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts only",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    slugs = [s for s in QUICK_INTERACT_SLUGS if not args.only or s in args.only]
    if args.only:
        unknown = set(args.only) - set(QUICK_INTERACT_SLUGS)
        if unknown:
            print(f"Unknown slugs: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
    out_dir = Path(args.output).resolve() if args.output else default_action_output_dir()

    if args.dry_run:
        for slug in slugs:
            print(f"{slug}: {hover_icon_prompt(slug)}")
        return 0

    client = ImageGenMcpClient(args.mcp_url or default_mcp_url())
    client.initialize()
    try:
        for slug in slugs:
            out_path = out_dir / f"{slug}.png"
            print(f"Generating {slug} -> {out_path}", flush=True)
            generated = client.generate_image(
                prompt=hover_icon_prompt(slug),
                size="512x512",
                quality=args.quality,
                negative_prompt=action_icon_negative(slug=slug),
                output_format="png",
                model=args.model,
            )
            icon = prepare_hover_icon(generated.image, size=args.size)
            out_dir.mkdir(parents=True, exist_ok=True)
            save_pil(icon, out_path, format="PNG")
            stats = optimize_icon_for_web(out_path, max_dim=args.size)
            print(
                f"  wrote {out_path} ({icon.mode}, {icon.size[0]}x{icon.size[1]}, "
                f"-{stats['bytes_before'] - stats['bytes_after']} bytes optimized)",
                flush=True,
            )
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
