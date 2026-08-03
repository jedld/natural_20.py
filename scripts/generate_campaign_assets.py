#!/usr/bin/env python3
"""Generate campaign NPC tokens and login/title backgrounds via Image Gen MCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.image_gen.campaign_assets import generate_campaign_assets, status_probe
from natural20.image_gen.mcp_client import default_mcp_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate circular NPC tokens and campaign title/login backgrounds "
            "using the local Image Gen MCP server (default http://127.0.0.1:8020/mcp)."
        )
    )
    parser.add_argument(
        "--campaign",
        required=True,
        help="Campaign directory (e.g. user_levels/outcasts_path)",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help=f"Image Gen MCP endpoint (default: {default_mcp_url()})",
    )
    parser.add_argument(
        "--tokens",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate circular NPC tokens into assets/token_<kind>.png (default: true)",
    )
    parser.add_argument(
        "--background",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate login/title background from index.json login_background (default: true)",
    )
    parser.add_argument(
        "--portraits",
        action="store_true",
        help="Also generate selectable character portraits under assets/characters/",
    )
    parser.add_argument(
        "--full-body",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate NPC full-body sheet images when full_body_scene/full_body_image is set (default: true)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing assets",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned generations without calling the MCP",
    )
    parser.add_argument(
        "--update-yaml",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write token_image onto NPC YAML files (default: true)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to NPC kind / portrait name (repeatable)",
    )
    parser.add_argument(
        "--token-size",
        type=int,
        default=256,
        help="Circular token pixel size (default: 256, matches character builder)",
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    campaign = Path(args.campaign)
    if not campaign.is_dir():
        print(f"Campaign not found: {campaign}", file=sys.stderr)
        return 2

    if args.status:
        probe = status_probe(args.mcp_url)
        print(json.dumps(probe, indent=2, default=str)[:4000])
        return 0 if probe.get("ok") else 1

    report = generate_campaign_assets(
        campaign,
        mcp_url=args.mcp_url,
        tokens=args.tokens,
        background=args.background,
        portraits=args.portraits,
        full_body=args.full_body,
        force=args.force,
        update_yaml=args.update_yaml,
        token_size=args.token_size,
        dry_run=args.dry_run,
        only=args.only or None,
        quality=args.quality,
        model=args.model,
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
