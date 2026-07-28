#!/usr/bin/env python3
"""
Spell Scroll Maker - overlay a spell image on a scroll background.

Delegates compositing to natural20.image_gen.spell_scroll_icons.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.image_gen.spell_scroll_icons import (  # noqa: E402
    DEFAULT_SCROLL_BACKGROUND,
    DEFAULT_SPELL_SCROLL_SCALE,
    overlay_spell_on_scroll,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Overlay a spell image on a scroll background")
    parser.add_argument("target_image", help="Path to the spell image to overlay")
    parser.add_argument(
        "--background",
        "-b",
        default=str(DEFAULT_SCROLL_BACKGROUND),
        help="Path to the background image",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="output.png",
        help="Path for the output image (default: output.png)",
    )
    parser.add_argument(
        "--scale",
        "-s",
        type=float,
        default=DEFAULT_SPELL_SCROLL_SCALE,
        help=f"Scale factor for the target image (default: {DEFAULT_SPELL_SCROLL_SCALE})",
    )
    parser.add_argument(
        "--position",
        "-p",
        type=int,
        nargs=2,
        metavar=("X", "Y"),
        help="Optional X Y position to place the target image",
    )
    args = parser.parse_args()

    target_path = Path(args.target_image)
    background_path = Path(args.background)
    output_path = Path(args.output)

    if not target_path.is_file():
        raise SystemExit(f"Error: Target image '{target_path}' not found")
    if not background_path.is_file():
        raise SystemExit(f"Error: Background image '{background_path}' not found")

    result = overlay_spell_on_scroll(
        background_path,
        target_path,
        scale_factor=args.scale,
        position=tuple(args.position) if args.position else None,
    )
    result.save(output_path, "PNG")
    print(f"Successfully created {output_path}")


if __name__ == "__main__":
    main()
