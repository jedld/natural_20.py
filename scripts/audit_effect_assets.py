#!/usr/bin/env python3
"""Audit map tile effect icons against runtime *Effect* class slugs.

The VTT loads ``webapp/static/assets/effect/<slug>.png`` where *slug* is
``str(effect).lower()`` for active tile effects. This script scans Python
effect classes, flags invalid slugs (spaces, parentheses, missing ``__str__``),
and reports missing PNG files.

Use with ``scripts/generate_game_icons.py`` to materialize gaps via spell-art
copy, placeholders, or Image Gen MCP.

Examples::

    # JSON report (exit 1 when slugs or assets are broken)
    python scripts/audit_effect_assets.py

    # Create missing icons from spell art / placeholders (no GPU)
    python scripts/audit_effect_assets.py --fix-fallback

    # Then generate any remaining via MCP
    python scripts/generate_game_icons.py --no-items --no-spells --no-actions \\
        --effect-fallback mcp --only light
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.image_gen.effect_assets import (  # noqa: E402
    audit_effect_assets,
    audit_report_as_dict,
    discover_runtime_effect_refs,
    materialize_effect_icon,
)
from natural20.image_gen.game_icons import default_effect_output_dir  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--effect-output",
        default=None,
        help="Override effect icon directory (default: webapp/static/assets/effect)",
    )
    parser.add_argument(
        "--fix-fallback",
        action="store_true",
        help="Write missing icons using spell-art copy or placeholders (no MCP)",
    )
    parser.add_argument(
        "--fallback-mode",
        choices=("auto", "copy", "placeholder"),
        default="auto",
        help="Fallback strategy when --fix-fallback is set (default: auto)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit audit/fix to slug (repeatable)",
    )
    parser.add_argument(
        "--fail-on-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit 1 when assets are missing (default: on)",
    )
    parser.add_argument(
        "--fail-on-invalid-slug",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit 1 when a class resolves to an invalid tile slug (default: on)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    effect_output = (
        Path(args.effect_output).resolve()
        if args.effect_output
        else default_effect_output_dir()
    )

    audit = audit_effect_assets(effect_output_dir=effect_output)
    only = {slug.lower() for slug in args.only} if args.only else None

    if args.fix_fallback:
        refs = discover_runtime_effect_refs(effect_output_dir=effect_output)
        for ref in refs:
            if only and ref.key.lower() not in only:
                continue
            if ref.output_path.is_file():
                continue
            ok, note = materialize_effect_icon(
                ref,
                mode=args.fallback_mode,
                effect_output_dir=effect_output,
            )
            print(f"[{'OK' if ok else 'SKIP'}] {ref.key}: {note}", flush=True)
        audit = audit_effect_assets(effect_output_dir=effect_output)

    payload = audit_report_as_dict(audit)
    if only:
        payload["effects"] = [e for e in payload["effects"] if e["slug"] in only]
        payload["missing_assets"] = [
            e for e in payload["missing_assets"] if e["slug"] in only
        ]
        payload["invalid_slugs"] = [
            e for e in payload["invalid_slugs"] if e["slug"] in only
        ]
        payload["ok"] = not payload["invalid_slugs"] and not payload["missing_assets"]

    print(json.dumps(payload, indent=2))

    code = 0
    if args.fail_on_invalid_slug and payload["invalid_slugs"]:
        code = 1
    if args.fail_on_missing and payload["missing_assets"]:
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
