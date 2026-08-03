#!/usr/bin/env python3
"""Generate NPC image_gallery assets with per-entry or CLI-customized prompts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.image_gen.campaign_assets import (
    ensure_npc_image_gallery_entry,
    find_npc_def,
    generate_npc_gallery_images,
    npc_gallery_entries,
    status_probe,
)
from natural20.image_gen.mcp_client import default_mcp_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate NPC image_gallery JPEGs via Image Gen MCP. "
            "Prompts come from each gallery entry's gallery_prompt in YAML, "
            "or from --prompt / --prompt-file overrides."
        )
    )
    parser.add_argument("--campaign", required=True, help="Campaign directory")
    parser.add_argument(
        "--npc",
        required=True,
        help="NPC kind or YAML stem (e.g. pip_barmaid or Pip)",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help=f"Image Gen MCP endpoint (default: {default_mcp_url()})",
    )
    parser.add_argument(
        "--id",
        action="append",
        default=[],
        dest="entry_ids",
        help="Limit to gallery id(s) from image_gallery (repeatable)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Asset path under campaign/assets/ for a one-off --id (e.g. portraits/pip_scene.jpg)",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Label for one-off gallery entry when using --append-yaml",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="JRPG portrait description metadata for one-off / --append-yaml",
    )
    parser.add_argument(
        "--scene",
        default=None,
        help="gallery_scene key for auto-built prompts when --prompt is omitted",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Override diffusion prompt for the selected --id",
    )
    parser.add_argument(
        "--negative-prompt",
        default=None,
        help="Extra negative prompt terms for the selected --id",
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="Read override prompt text from a file (for long customized prompts)",
    )
    parser.add_argument(
        "--negative-file",
        default=None,
        help="Read extra negative prompt text from a file",
    )
    parser.add_argument(
        "--append-yaml",
        action="store_true",
        help="Upsert a one-off --id/--output entry into the NPC YAML image_gallery",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing gallery images",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned prompts without calling the MCP",
    )
    parser.add_argument(
        "--no-update-yaml",
        action="store_true",
        help="Do not write gallery_prompt metadata back to NPC YAML",
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
    parser.add_argument(
        "--list",
        action="store_true",
        help="List image_gallery entries for the NPC and exit",
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

    npc = find_npc_def(campaign, args.npc)
    if npc is None:
        print(f"NPC not found: {args.npc}", file=sys.stderr)
        return 2

    if args.list:
        for entry in npc_gallery_entries(npc):
            print(
                f"{entry.get('id')}: {entry.get('image')} "
                f"({entry.get('label')}) — {entry.get('description') or 'no description'}"
            )
        return 0

    prompt_override = args.prompt
    if args.prompt_file:
        prompt_override = Path(args.prompt_file).read_text(encoding="utf-8").strip()

    negative_override = args.negative_prompt
    if args.negative_file:
        negative_override = Path(args.negative_file).read_text(encoding="utf-8").strip()

    custom_entries = None
    prompt_overrides: dict[str, str] = {}
    negative_overrides: dict[str, str] = {}

    if args.entry_ids and len(args.entry_ids) == 1 and (args.output or prompt_override or negative_override):
        entry_id = args.entry_ids[0]
        if prompt_override:
            prompt_overrides[entry_id] = prompt_override
        if negative_override:
            negative_overrides[entry_id] = negative_override
        if args.output:
            one_off = {
                "id": entry_id,
                "label": args.label or entry_id.replace("_", " ").title(),
                "image": args.output.replace("\\", "/"),
            }
            if args.description:
                one_off["description"] = args.description
            if prompt_override:
                one_off["gallery_prompt"] = prompt_override
            if negative_override:
                one_off["gallery_negative_prompt"] = negative_override
            if args.scene:
                one_off["gallery_scene"] = args.scene
            custom_entries = [one_off]
            if args.append_yaml and not args.dry_run:
                ensure_npc_image_gallery_entry(campaign, npc, one_off)

    report = generate_npc_gallery_images(
        campaign,
        args.npc,
        mcp_url=args.mcp_url,
        entry_ids=args.entry_ids or None,
        force=args.force,
        dry_run=args.dry_run,
        update_yaml=not args.no_update_yaml,
        quality=args.quality,
        model=args.model,
        custom_entries=custom_entries,
        prompt_overrides=prompt_overrides or None,
        negative_overrides=negative_overrides or None,
    )

    for result in report.results:
        status = "ERROR" if result.error else ("SKIP" if result.skipped else "WRITE")
        detail = result.error or result.reason or str(result.output_path)
        print(f"[{status}] gallery:{result.key} — {detail}", flush=True)

    print(
        f"Done. written={len(report.written)} skipped={sum(1 for r in report.results if r.skipped)} "
        f"errors={len(report.errors)}",
        flush=True,
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
