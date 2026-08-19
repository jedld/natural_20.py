#!/usr/bin/env python3
"""Import a battlemap image into Natural20 map YAML (humans and agents).

Slice the image tile-by-tile, classify each tile with a VLM (or heuristic
priors), keep an identification log for neighbor-aware cleanup, then overlay
adventure-guide NPCs, notes, and map_annotations.

Examples:

  # Inspect knobs JSON schema (agent tool calling)
  python scripts/import_battlemap.py --print-schema

  # Local, no VLM (PIL heuristics only) — good smoke test
  python scripts/import_battlemap.py assets/maps/tavern_22x17.png \\
      --provider heuristic --name Tavern -o maps/tavern.yml --workdir /tmp/tavern_import

  # Ollama vision model
  python scripts/import_battlemap.py user_levels/death_house/assets/maps/tavern_night.png \\
      --width 40 --height 30 --provider ollama --model llava \\
      --adventure user_levels/death_house/references/chapter_1/tavern.md \\
      --campaign user_levels/death_house --map-id tavern_imported \\
      -o user_levels/death_house/maps/tavern_imported.yml

  # Resume after classifying, run adventure+refine only
  python scripts/import_battlemap.py IMAGE --resume --workdir /tmp/tavern_import --phase refine
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.map_import import ImportBundle, ImportKnobs, import_battlemap, knobs_json_schema


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import a battlemap image into Natural20 map YAML via tile-wise VLM classification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("image", nargs="?", help="Battlemap image (png/jpg/webp)")
    parser.add_argument("--print-schema", action="store_true", help="Print JSON schema for LLM/agent tool calling")
    parser.add_argument("--knobs-json", help="Load knobs from a JSON file (overrides flags)")
    parser.add_argument("--width", type=int, help="Grid width in tiles")
    parser.add_argument("--height", type=int, help="Grid height in tiles")
    parser.add_argument("--tile-size", type=int, help="Pixels per tile (infer width/height from image)")
    parser.add_argument("--offset", default="0,0", help="Image crop origin x,y in pixels")
    parser.add_argument("--pad-ratio", type=float, default=0.25, help="Neighbor padding on each tile crop")
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "anthropic", "mock", "heuristic"],
        default="heuristic",
        help="VLM backend (default heuristic = no network)",
    )
    parser.add_argument("--model", help="Vision model name")
    parser.add_argument("--base-url", help="Provider base URL (Ollama / OpenAI-compatible)")
    parser.add_argument("--api-key", help="API key (otherwise env OPENAI_API_KEY / ANTHROPIC_API_KEY)")
    parser.add_argument("--confidence", type=float, default=0.55, dest="confidence_threshold")
    parser.add_argument("--max-tiles", type=int, help="Classify at most N tiles (debug)")
    parser.add_argument("--skip-vlm", action="store_true", help="Force heuristic provider")
    parser.add_argument("--no-mosaic", action="store_true", help="Send the single padded tile instead of a 3x3 mosaic")
    parser.add_argument("--name", default="Imported Map")
    parser.add_argument("--description", default="")
    parser.add_argument("--map-id", default="", help="Output map id (filename stem when writing into a campaign)")
    parser.add_argument("--campaign", help="Campaign root; used with --map-id for default output path")
    parser.add_argument("--adventure", action="append", default=[], help="Adventure markdown/text file (repeatable)")
    parser.add_argument("--adventure-text", default="", help="Inline adventure excerpt")
    parser.add_argument("--illumination", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--calibrate-grid",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Nudge offset so grid lines sit on dark ink (default: on). Use --no-calibrate-grid to skip.",
    )
    parser.add_argument(
        "--split-panels",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Detect multiple floors on one page and import each crop (default: on). "
            "Use --no-split-panels to treat the image as a single map."
        ),
    )
    parser.add_argument("--workdir", help="Inspectable checkpoint directory (tiles, ascii, JSON logs)")
    parser.add_argument(
        "--phase",
        default="all",
        choices=["slice", "classify", "consistency", "adventure", "refine", "export", "all"],
        help="Stop after this phase (earlier phases still run unless --resume)",
    )
    parser.add_argument("--resume", action="store_true", help="Reuse classifications.json in --workdir")
    parser.add_argument("--seed-map", default="", help="YAML map.base to seed occupancy before the VLM second opinion")
    parser.add_argument("-o", "--output", help="Write map YAML to this path")
    parser.add_argument("--report", help="Write machine-readable report JSON")
    parser.add_argument("--json", action="store_true", dest="json_stdout", help="Print report JSON only")
    return parser


def _parse_offset(raw: str) -> list[int]:
    parts = [p.strip() for p in raw.replace(" ", "").split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--offset must be x,y")
    return [int(parts[0]), int(parts[1])]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.print_schema:
        print(json.dumps(knobs_json_schema(), indent=2))
        return 0

    if args.knobs_json:
        data = json.loads(Path(args.knobs_json).read_text(encoding="utf-8"))
        knobs = ImportKnobs.from_dict(data)
        if args.image:
            knobs.image = args.image
    else:
        if not args.image:
            parser.error("image is required (or pass --print-schema / --knobs-json)")
        knobs = ImportKnobs(
            image=args.image,
            width=args.width,
            height=args.height,
            tile_size=args.tile_size,
            image_offset_px=_parse_offset(args.offset),
            pad_ratio=args.pad_ratio,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            confidence_threshold=args.confidence_threshold,
            max_tiles=args.max_tiles,
            skip_vlm=args.skip_vlm,
            include_mosaic=not args.no_mosaic,
            name=args.name,
            description=args.description,
            map_id=args.map_id,
            adventure_text=args.adventure_text,
            adventure_files=list(args.adventure),
            campaign=args.campaign,
            illumination=args.illumination,
            timeout=args.timeout,
            seed_map=args.seed_map,
        )
        if args.calibrate_grid is not None:
            knobs.calibrate_grid = args.calibrate_grid
        if args.split_panels is not None:
            knobs.split_panels = args.split_panels

    if args.knobs_json and args.calibrate_grid is not None:
        knobs.calibrate_grid = args.calibrate_grid
    if args.knobs_json and args.split_panels is not None:
        knobs.split_panels = args.split_panels
    if args.seed_map:
        knobs.seed_map = args.seed_map

    result = import_battlemap(
        knobs,
        workdir=args.workdir,
        stop_after=args.phase,
        resume=args.resume,
        output=args.output,
    )
    report = result.to_dict()
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.json_stdout:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))
        if isinstance(result, ImportBundle):
            for item in result.results:
                print(f"--- {item.knobs.name} ---", file=sys.stderr)
                print(item.grid.ascii_map(), file=sys.stderr)
            print(f"workdir: {result.workdir}", file=sys.stderr)
            for item in result.results:
                if item.output_yaml:
                    print(f"yaml: {item.output_yaml}", file=sys.stderr)
        else:
            print(result.grid.ascii_map(), file=sys.stderr)
            print(f"workdir: {result.workdir}", file=sys.stderr)
            if result.output_yaml:
                print(f"yaml: {result.output_yaml}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
