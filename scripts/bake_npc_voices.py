#!/usr/bin/env python3
"""Pre-bake stable NPC voice reference clips for a campaign.

Generates ``assets/voice_samples/<npc_uid>.wav`` (or ``.mp3`` for ElevenLabs)
under the campaign root. Default engine is Qwen3 VoiceDesign (English campaigns).
CosyVoice (``--bake-provider cosyvoice``) needs an English prompt WAV.
ElevenLabs (``--bake-provider elevenlabs``) uses Voice Design and writes MP3;
runtime TTS stays on Qwen3 / qwen3_vllm.

Example:
  python scripts/bake_npc_voices.py user_levels/death_house --bake-provider elevenlabs --force

Loads ``webapp/.env`` automatically (TTS_DEVICE, QWEN3_TTS_MODEL, ELEVENLABS_API_KEY).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBAPP_DIR = REPO_ROOT / "n20-webapp"
if WEBAPP_DIR.is_dir() and str(WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(WEBAPP_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _dedupe_candidates(candidates):
    """Keep one candidate per entity uid; prefer map instances over npc type defs."""
    by_uid = {}
    for candidate in candidates:
        uid = str(candidate.entity_uid or "").strip()
        if not uid:
            # Type archetypes without a stable uid would bake type_<kind>.mp3.
            if str(candidate.key).startswith("type_"):
                continue
            uid = str(candidate.key or "").strip()
        if not uid:
            continue
        existing = by_uid.get(uid)
        if existing is None:
            by_uid[uid] = candidate
            continue
        existing_type = str(existing.key).startswith("type_")
        incoming_type = str(candidate.key).startswith("type_")
        if existing_type and not incoming_type:
            by_uid[uid] = candidate
    return list(by_uid.values())


def _entity_stub(campaign_root: Path, candidate):
    from types import SimpleNamespace

    from natural20.tts.campaign_voice_profiles import load_campaign_voice_asset

    uid = candidate.entity_uid or candidate.key
    asset = load_campaign_voice_asset(
        campaign_root,
        entity_uid=uid,
        npc_type=candidate.npc_type,
    )
    props = dict(candidate.data)
    if isinstance(asset, dict) and isinstance(asset.get("voice"), dict):
        # YAML is the bake source of truth. Generated voice-profile assets can
        # carry a stale accent/prompt from an older generator run.
        yaml_voice = props.get("voice") if isinstance(props.get("voice"), dict) else {}
        props["voice"] = {**asset["voice"], **yaml_voice}
    return SimpleNamespace(
        entity_uid=uid,
        properties=props,
        session=SimpleNamespace(root_path=str(campaign_root)),
        npc_type=candidate.npc_type,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bake NPC voice reference clips for a campaign")
    parser.add_argument("campaign_root", type=Path, help="Path to campaign folder (game.yml root)")
    parser.add_argument("--force", action="store_true", help="Re-bake even when sample WAV already exists")
    parser.add_argument("--provider", default=None, help="TTS provider (default: TTS_PROVIDER env or qwen3)")
    parser.add_argument(
        "--bake-provider",
        default=None,
        help="Engine that synthesizes reference clips only "
        "(cosyvoice|qwen3|elevenlabs). Default: N20_TTS_BAKE_PROVIDER or --provider. "
        "Runtime TTS is unchanged. elevenlabs is bake-only (not TTS_PROVIDER).",
    )
    parser.add_argument("--device", default=None, help="cuda|gpu|cpu (default: TTS_DEVICE env)")
    parser.add_argument(
        "--include-types",
        action="store_true",
        help="Also bake npcs/*.yml archetypes (type_<kind>.wav). Default: map instances only.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to NPC label, type, entity_uid, or profile key (repeatable)",
    )
    args = parser.parse_args()

    from webapp.tts.env_config import configure_tts_cuda_device, load_webapp_dotenv

    load_webapp_dotenv()
    configure_tts_cuda_device()

    os.environ.setdefault("N20_TTS_BAKE_VOICES", "1")

    campaign_root = args.campaign_root.resolve()
    if not (campaign_root / "game.yml").is_file():
        print(f"Not a campaign root (missing game.yml): {campaign_root}", file=sys.stderr)
        return 1

    bake_provider = (
        args.bake_provider
        or os.environ.get("N20_TTS_BAKE_PROVIDER", "").strip()
        or args.provider
        or os.environ.get("TTS_PROVIDER", "qwen3")
    )
    bake_provider = str(bake_provider).strip().lower()
    device = args.device or os.environ.get("TTS_DEVICE", "cpu")

    from natural20.tts.campaign_voice_profiles import discover_voice_candidates
    from webapp.tts.manager import TTSManager
    from webapp.tts.npc_voice import build_voice_profile_from_entity
    from webapp.tts.voice_baking import BAKE_ONLY_PROVIDERS, should_bake_voice_profile, voice_sample_path

    runtime_provider = (
        args.provider
        or os.environ.get("TTS_PROVIDER", "qwen3")
    ).strip().lower()
    if bake_provider in BAKE_ONLY_PROVIDERS:
        if runtime_provider in BAKE_ONLY_PROVIDERS:
            runtime_provider = "mock_qwen3"
        print(
            f"[bake] bake_provider={bake_provider} device={device} "
            f"runtime_TTS_PROVIDER={runtime_provider}",
            flush=True,
        )
        manager = TTSManager(device=device)
        manager.initialize(provider=runtime_provider)
    else:
        print(
            f"[bake] bake_provider={bake_provider} device={device} "
            f"runtime_TTS_PROVIDER={os.environ.get('TTS_PROVIDER', '(unset)')}",
            flush=True,
        )
        manager = TTSManager(device=device)
        manager.initialize(provider=bake_provider)

    candidates = discover_voice_candidates(
        campaign_root,
        include_types=args.include_types,
        include_maps=True,
        only=set(args.only) if args.only else None,
    )
    candidates = _dedupe_candidates(candidates)
    if not candidates:
        print("No voice candidates found.")
        return 0

    baked = 0
    skipped = 0
    failed = 0
    for candidate in candidates:
        entity = _entity_stub(campaign_root, candidate)
        uid = str(getattr(entity, "entity_uid", "") or "").strip()
        profile = build_voice_profile_from_entity(entity)
        if not should_bake_voice_profile(profile) and not args.force:
            skipped += 1
            continue
        sample = voice_sample_path(str(campaign_root), uid)
        try:
            path = manager.bake_voice_for_profile(
                profile,
                force=args.force or bool(sample and sample.is_file()),
                provider_override=bake_provider,
            )
            if path and Path(path).is_file():
                print(f"[baked] {uid}: {path}")
                baked += 1
            else:
                print(f"[warn] {uid}: no sample written", file=sys.stderr)
                failed += 1
        except Exception as exc:
            print(f"[error] {uid}: {exc}", file=sys.stderr)
            failed += 1

    print(f"Done. baked={baked} skipped={skipped} failed={failed} candidates={len(candidates)}")
    return 1 if failed and not baked else 0


if __name__ == "__main__":
    raise SystemExit(main())
