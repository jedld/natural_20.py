#!/usr/bin/env python3
"""Pre-bake stable NPC voice reference clips for a campaign.

Generates ``assets/voice_samples/<npc_uid>.wav`` under the campaign root using
the Qwen3 VoiceDesign model, for timbre-locked clone synthesis at runtime.

Example:
  cd webapp && python ../scripts/bake_npc_voices.py ../user_levels/wild_sheep_chase

Loads ``webapp/.env`` automatically (TTS_DEVICE, QWEN3_TTS_MODEL, etc.).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBAPP_DIR = REPO_ROOT / "webapp"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
        props["voice"] = {**props.get("voice", {}), **asset["voice"]}
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
    parser.add_argument("--device", default=None, help="cuda|gpu|cpu (default: TTS_DEVICE env)")
    parser.add_argument(
        "--include-types",
        action="store_true",
        help="Also bake npcs/*.yml archetypes (type_<kind>.wav). Default: map instances only.",
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

    provider = args.provider or os.environ.get("TTS_PROVIDER", "qwen3")
    device = args.device or os.environ.get("TTS_DEVICE", "cpu")

    from natural20.tts.campaign_voice_profiles import discover_voice_candidates
    from webapp.tts.manager import TTSManager
    from webapp.tts.npc_voice import build_voice_profile_from_entity
    from webapp.tts.voice_baking import should_bake_voice_profile, voice_sample_path

    print(
        f"[bake] provider={provider} device={device} model={os.environ.get('QWEN3_TTS_MODEL', '(default)')}",
        flush=True,
    )
    manager = TTSManager(device=device)
    manager.initialize(provider=provider)

    candidates = discover_voice_candidates(
        campaign_root,
        include_types=args.include_types,
        include_maps=True,
    )
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
            continue
        sample = voice_sample_path(str(campaign_root), uid)
        if sample and sample.is_file() and not args.force:
            print(f"[skip] {uid}: {sample}")
            skipped += 1
            continue
        try:
            path = manager.bake_voice_for_profile(
                profile,
                force=args.force,
                provider_override=provider,
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
