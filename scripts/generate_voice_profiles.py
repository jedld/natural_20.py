#!/usr/bin/env python3
"""Generate NPC voice profiles for a campaign and save them as campaign assets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.tts.campaign_voice_profiles import (  # noqa: E402
    VOICE_PROFILES_DIR,
    VoiceProfileGenerationMode,
    generate_voice_profiles,
    make_voice_profile_llm_sender,
    resolve_generation_mode,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate TTS voice profiles for campaign NPCs from backstory, "
            "descriptions, and map overrides. Writes assets/voice_profiles/*.yml "
            "and an index.json (optionally patches npcs/*.yml)."
        )
    )
    parser.add_argument(
        "--campaign",
        required=True,
        help="Campaign directory (e.g. templates or user_levels/death_house)",
    )
    parser.add_argument(
        "--mode",
        choices=[m.value for m in VoiceProfileGenerationMode],
        default=None,
        help=(
            "Profile authoring mode: heuristic (keyword rules) or llm (LLM-guided). "
            "Defaults to N20_VOICE_PROFILE_MODE, campaign game.yml tts.voice_profile_mode, "
            "or heuristic."
        ),
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Shortcut for --mode llm",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="In LLM mode, do not fall back to heuristics when the model fails",
    )
    parser.add_argument(
        "--llm-provider",
        choices=["npc", "dm"],
        default=None,
        help=(
            "Which LLM env vars to use in LLM mode (default: npc — NPC_LLM_* then DM). "
            "Override globally with N20_VOICE_PROFILE_LLM=npc|dm"
        ),
    )
    parser.add_argument(
        "--strategy",
        default="auto",
        choices=["auto", "clone", "design", "preset", "instruct"],
        help="Default voice.strategy written into generated profiles (default: auto)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Default voice.provider (e.g. qwen3, cosyvoice)",
    )
    parser.add_argument(
        "--maps-only",
        action="store_true",
        help="Only process named NPCs from map legend overrides",
    )
    parser.add_argument(
        "--types-only",
        action="store_true",
        help="Only process campaign npcs/*.yml type definitions",
    )
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Include generic creature types without dialog/backstory",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to NPC label, type, entity_uid, or profile key (repeatable)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when voice.prompt already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned profiles without writing files",
    )
    parser.add_argument(
        "--update-yaml",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Also merge voice blocks into campaign npcs/*.yml type files",
    )
    parser.add_argument(
        "--no-assets",
        action="store_true",
        help="Skip writing assets/voice_profiles (use with --update-yaml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    campaign = Path(args.campaign).expanduser().resolve()
    if not campaign.is_dir():
        print(f"Campaign directory not found: {campaign}", file=sys.stderr)
        return 1
    if not (campaign / "game.yml").is_file():
        print(f"Campaign is missing game.yml: {campaign}", file=sys.stderr)
        return 1

    if args.llm_provider:
        import os

        os.environ["N20_VOICE_PROFILE_LLM"] = args.llm_provider

    cli_mode = "llm" if args.llm else args.mode
    mode = resolve_generation_mode(campaign, cli_mode=cli_mode)
    llm_send = make_voice_profile_llm_sender() if mode == VoiceProfileGenerationMode.LLM else None

    report = generate_voice_profiles(
        campaign,
        mode=mode,
        llm_send=llm_send,
        heuristic_fallback=not args.no_fallback,
        default_strategy=args.strategy,
        default_provider=args.provider,
        include_types=not args.maps_only,
        include_maps=not args.types_only,
        only=args.only,
        all_types=args.all_types,
        force=args.force,
        dry_run=args.dry_run,
        update_yaml=args.update_yaml,
        write_assets=not args.no_assets,
    )

    if args.json:
        payload = {
            "campaign": str(campaign),
            "mode": mode.value,
            "written": [
                {
                    "profile_id": r.profile_id,
                    "label": r.label,
                    "npc_type": r.npc_type,
                    "source": r.source,
                    "generator_mode": r.generator_mode,
                    "voice": r.voice,
                }
                for r in report.written
            ],
            "skipped": [
                {"profile_id": r.profile_id, "label": r.label, "reason": r.reason}
                for r in report.skipped
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"Campaign: {campaign}")
        print(f"Mode: {mode.value}")
        print(f"Output dir: {campaign / VOICE_PROFILES_DIR}")
        for result in report.written:
            prompt = (result.voice or {}).get("prompt", "")
            print(f"  + [{result.generator_mode}] {result.profile_id}: {prompt}")
        for result in report.skipped:
            print(f"  - {result.profile_id}: {result.reason}")
        print(f"Written: {len(report.written)}  Skipped: {len(report.skipped)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
