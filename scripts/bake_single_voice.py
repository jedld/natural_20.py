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
WEBAPP_DIR = REPO_ROOT / "webapp"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Bake a single NPC voice for a campaign")
    parser.add_argument("npc_uid", help="NPC uid (e.g. garret_guard)")
    parser.add_argument("campaign_root", type=Path, help="Path to campaign folder (game.yml root)")
    parser.add_argument("--provider", default="qwen3", help="TTS provider (default: qwen3)")
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
    from webapp.tts.voice_baking import voice_sample_path

    provider = args.provider
    print(f"[bake] provider={provider} device={device} npc={args.npc_uid}", flush=True)

    manager = TTSManager(device=device)
    manager.initialize(provider=provider)

    # Build a minimal voice profile for just this NPC
    ref_text = args.ref_text or os.environ.get(
        "N20_TTS_BAKE_SAMPLE_TEXT",
        "A deep, gravelly, and rough voice for dialogue. Warm but authoritative, just as I always speak."
    )

    profile = VoiceProfile(
        npc_uid=args.npc_uid,
        provider=provider,
        campaign_root=str(campaign_root),
        design_prompt=ref_text,
        strategy=VoiceStrategy.DESIGN,
        language="en",
    )

    try:
        path = manager.bake_voice_for_profile(
            profile,
            force=True,
            provider_override=provider,
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
