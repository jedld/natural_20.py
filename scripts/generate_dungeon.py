#!/usr/bin/env python3
"""Generate a procedural Natural20 dungeon map from LLM-friendly knobs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.dungeon_gen import (
    generate_dungeon,
    generate_from_mission,
    knobs_from_theme,
    knobs_json_schema,
)
from natural20.dungeon_gen.knobs import GeneratorKnobs, ObjectiveSpec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Procedural dungeon generator with traversability & aesthetics checks.",
    )
    parser.add_argument("--theme", default="dungeon", help="Theme preset (dungeon, cave, sewer, …)")
    parser.add_argument("--algorithm", choices=["bsp", "rooms_graph", "cellular", "hybrid"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--rooms", type=int, dest="room_count")
    parser.add_argument("--loop-ratio", type=float)
    parser.add_argument("--linearity", type=float)
    parser.add_argument("--enemy-density", type=float)
    parser.add_argument("--trap-density", type=float)
    parser.add_argument("--chest-density", type=float)
    parser.add_argument("--name", default=None)
    parser.add_argument("--description", default=None)
    parser.add_argument("--mission", default="", help="Mission blurb stored in map description")
    parser.add_argument(
        "--objective",
        action="append",
        default=[],
        help="Objective as id:kind[:room_role[:depth]] (repeatable)",
    )
    parser.add_argument("--knobs-json", help="Path to JSON knobs file (overrides flags)")
    parser.add_argument("--print-schema", action="store_true", help="Print JSON schema for LLM tools")
    parser.add_argument("-o", "--output", help="Write map YAML to this path")
    parser.add_argument("--report", help="Write generation quality report JSON")
    parser.add_argument("--render", help="Also render a PNG via map_image")
    parser.add_argument("--require-aesthetics", type=float, default=0.0)
    parser.add_argument("--no-traverse-gate", action="store_true")
    return parser


def _parse_objective(raw: str) -> ObjectiveSpec:
    parts = raw.split(":")
    obj_id = parts[0]
    kind = parts[1] if len(parts) > 1 else "interactive_object"
    room_role = parts[2] if len(parts) > 2 and parts[2] not in {"", "any"} else None
    depth = parts[3] if len(parts) > 3 else "any"
    return ObjectiveSpec(id=obj_id, kind=kind, room_role=room_role, depth=depth)  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.print_schema:
        print(json.dumps(knobs_json_schema(), indent=2))
        return 0

    if args.knobs_json:
        data = json.loads(Path(args.knobs_json).read_text(encoding="utf-8"))
        knobs = GeneratorKnobs.from_dict(data)
    else:
        overrides = {}
        for key in (
            "algorithm",
            "seed",
            "width",
            "height",
            "room_count",
            "loop_ratio",
            "linearity",
            "enemy_density",
            "trap_density",
            "chest_density",
        ):
            value = getattr(args, key, None)
            if value is not None:
                overrides[key] = value
        if args.name:
            overrides["name"] = args.name
        if args.description or args.mission:
            overrides["description"] = args.description or args.mission
        overrides["require_aesthetics_score"] = args.require_aesthetics
        overrides["ensure_traversable"] = not args.no_traverse_gate
        knobs = knobs_from_theme(args.theme, **overrides)
        if args.objective:
            knobs.objectives = [_parse_objective(item) for item in args.objective]

    result = generate_dungeon(knobs)

    summary = {
        "accepted": result.accepted,
        "attempts": result.attempts,
        "aesthetics": result.aesthetics.to_dict(),
        "traversability": result.traversability.to_dict(),
        "rooms": len(result.grid.rooms),
        "placements": len(result.grid.placements),
        "seed": result.grid.meta.get("seed"),
        "messages": result.messages,
    }
    print(json.dumps(summary, indent=2))

    if args.output:
        result.write_yaml(args.output)
        print(f"Wrote map YAML: {args.output}", file=sys.stderr)

    if args.report:
        Path(args.report).write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"Wrote report: {args.report}", file=sys.stderr)

    if args.render:
        from natural20.map_image.renderer import render_map_image

        if not args.output:
            print("error: --render requires --output YAML path", file=sys.stderr)
            return 2
        render_map_image(
            input_yaml=args.output,
            output=args.render,
            tile_size=48,
            skip_background_image=True,
        )
        print(f"Wrote render: {args.render}", file=sys.stderr)

    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
