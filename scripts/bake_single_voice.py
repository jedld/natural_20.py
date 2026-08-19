#!/usr/bin/env python3
"""Bake a single NPC voice reference clip using Qwen3 VoiceDesign.

Usage:
    cd n20-webapp/webapp && python ../../scripts/bake_single_voice.py garret_guard ../user_levels/wild_sheep_chase
"""

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
    parser = argparse.ArgumentParser(description="Bake a single NPC voice for a campaign")
    parser.add_argument("npc_uid", help="NPC uid (e.g. garret_guard)")
    parser.add_argument("campaign_root", type=Path, help="Path to campaign folder (game.yml root)")
    parser.add_argument("--provider", default=None, help="TTS provider (default: qwen3)")
    parser.add_argument(
        "--bake-provider",
        default=None,
        help="Engine that synthesizes the reference WAV (cosyvoice|qwen3). "
        "Default: N20_TTS_BAKE_PROVIDER or --provider.",
    )
    parser.add_argument("--device", default=None, help="cuda|gpu|cpu (default: TTS_DEVICE env)")
    parser.add_argument("--ref-text", default=None, help="Custom ref text for voice design prompt")
    args = parser.parse_args()

    from webapp.tts.env_config import configure_tts_cuda_device, load_webapp_dotenv

    load_webapp_dotenv()
    configure_tts_cuda_device()

    device = args.device or os.environ.get("TTS_DEVICE", "cpu")

    campaign_root = args.campaign_root.resolve()
    if not (campaign_root / "game.yml").is_file():
        print(f"Not a campaign root (missing game.yml): {campaign_root}", file=sys.stderr)
        return 1

    from webapp.tts.manager import TTSManager
    from webapp.tts.voice_profile import VoiceProfile, VoiceStrategy

    bake_provider = (
        args.bake_provider
        or os.environ.get("N20_TTS_BAKE_PROVIDER", "").strip()
        or args.provider
        or "qwen3"
    )
    print(f"[bake] bake_provider={bake_provider} device={device} npc={args.npc_uid}", flush=True)

    manager = TTSManager(device=device)
    manager.initialize(provider=bake_provider)

    from webapp.tts.npc_voice import build_voice_profile_from_entity
    from natural20.tts.campaign_voice_profiles import discover_voice_candidates

    candidates = discover_voice_candidates(
        campaign_root,
        include_types=True,
        include_maps=True,
        only={args.npc_uid},
    )
    if args.ref_text:
        os.environ["N20_TTS_BAKE_SAMPLE_TEXT"] = args.ref_text

    if candidates:
        profile = build_voice_profile_from_entity(_entity_stub(campaign_root, candidates[0]))
        profile.campaign_root = str(campaign_root)
    else:
        # Fallback when the uid is not in campaign YAML (ad-hoc bake).
        profile = VoiceProfile(
            npc_uid=args.npc_uid,
            prompt=args.ref_text or "Clear natural speaking voice for dialogue",
            provider=bake_provider,
            campaign_root=str(campaign_root),
            strategy=VoiceStrategy.DESIGN,
            language="en",
        )

    try:
        path = manager.bake_voice_for_profile(
            profile,
            force=True,
            provider_override=bake_provider,
        )
        if path and Path(path).is_file():
            print(f"[baked] {args.npc_uid}: {path}")
            return 0
        else:
            print(f"[warn] {args.npc_uid}: no sample written", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"[error] {args.npc_uid}: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
