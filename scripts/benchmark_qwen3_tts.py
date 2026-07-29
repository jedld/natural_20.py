#!/usr/bin/env python3
"""Benchmark Qwen3 TTS per-line latency for a campaign NPC.

Loads ``webapp/.env``, initializes the active TTS stack, registers one baked
NPC voice, and times synthesis passes (cold line, repeat line, line-cache hit).

Example:
  cd webapp && python ../scripts/benchmark_qwen3_tts.py ../user_levels/wild_sheep_chase --npc mara_bartender
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBAPP_DIR = REPO_ROOT / "webapp"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _entity_stub(campaign_root: Path, npc_uid: str, npc_type: str | None):
    from natural20.tts.campaign_voice_profiles import load_campaign_voice_asset

    asset = load_campaign_voice_asset(
        campaign_root,
        entity_uid=npc_uid,
        npc_type=npc_type,
    )
    props: dict = {}
    if isinstance(asset, dict) and isinstance(asset.get("voice"), dict):
        props["voice"] = dict(asset["voice"])
    return SimpleNamespace(
        entity_uid=npc_uid,
        properties=props,
        session=SimpleNamespace(root_path=str(campaign_root)),
        npc_type=npc_type,
    )


def _flash_attn_status() -> str:
    try:
        import flash_attn  # noqa: F401

        return f"installed ({getattr(flash_attn, '__version__', 'unknown')})"
    except ImportError:
        return "not installed"


def _wav_duration_seconds(path: Path) -> float | None:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        if info.samplerate <= 0:
            return None
        return float(info.frames) / float(info.samplerate)
    except Exception:
        return None


def _timed(label: str, fn):
    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start
    return elapsed, result


def _pick_npc_uid(campaign_root: Path, requested: str | None) -> tuple[str, str | None]:
    from webapp.tts.voice_baking import voice_sample_path

    if requested:
        return requested.strip(), None

    samples_dir = campaign_root / "assets" / "voice_samples"
    if samples_dir.is_dir():
        wavs = sorted(samples_dir.glob("*.wav"))
        if wavs:
            return wavs[0].stem, None

    from natural20.tts.campaign_voice_profiles import discover_voice_candidates

    candidates = discover_voice_candidates(campaign_root, include_maps=True)
    if candidates:
        first = candidates[0]
        return str(first.entity_uid or first.key), first.npc_type
    raise SystemExit(f"No NPC voice samples or candidates under {campaign_root}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Qwen3 TTS latency for one campaign NPC")
    parser.add_argument(
        "campaign_root",
        nargs="?",
        type=Path,
        default=REPO_ROOT / "user_levels" / "wild_sheep_chase",
        help="Campaign folder (default: user_levels/wild_sheep_chase)",
    )
    parser.add_argument("--npc", default=None, help="NPC entity uid (default: first baked sample)")
    parser.add_argument(
        "--text",
        default="Welcome to the tavern. What can I get for you tonight?",
        help="Dialogue line to synthesize",
    )
    parser.add_argument(
        "--alt-text",
        default="Keep your voice down — the guards are listening.",
        help="Second line for a non-cache synthesis pass",
    )
    parser.add_argument("--runs", type=int, default=1, help="Repeat synthesis count for the primary line")
    parser.add_argument("--no-line-cache", action="store_true", help="Disable N20_TTS_LINE_CACHE for this run")
    parser.add_argument("--device", default=None, help="Override TTS_DEVICE (cuda|gpu|cpu)")
    parser.add_argument("--provider", default=None, help="Override TTS_PROVIDER (default: env or qwen3)")
    args = parser.parse_args()

    from webapp.tts.env_config import configure_tts_cuda_device, load_webapp_dotenv

    load_webapp_dotenv()
    configure_tts_cuda_device()
    if args.no_line_cache:
        os.environ["N20_TTS_LINE_CACHE"] = "0"

    campaign_root = args.campaign_root.resolve()
    if not (campaign_root / "game.yml").is_file():
        print(f"Not a campaign root (missing game.yml): {campaign_root}", file=sys.stderr)
        return 1

    npc_uid, npc_type = _pick_npc_uid(campaign_root, args.npc)
    from webapp.tts.voice_baking import voice_sample_path
    from webapp.tts.manager import TTSManager
    from webapp.tts.npc_voice import build_voice_profile_from_entity
    from webapp.tts.synthesis_cache import line_cache_enabled, synthesis_cache_key

    sample_path = voice_sample_path(str(campaign_root), npc_uid)
    if not sample_path or not sample_path.is_file():
        print(
            f"No baked sample for {npc_uid}: {sample_path}\n"
            "Run: cd webapp && python ../scripts/bake_npc_voices.py "
            f"{campaign_root}",
            file=sys.stderr,
        )
        return 1

    provider = args.provider or os.environ.get("TTS_PROVIDER", "qwen3")
    device = args.device or os.environ.get("TTS_DEVICE", "cpu")

    print("=== Qwen3 TTS benchmark ===")
    print(f"campaign     : {campaign_root}")
    print(f"npc_uid      : {npc_uid}")
    print(f"sample       : {sample_path}")
    print(f"provider     : {provider}")
    print(f"device       : {device}")
    if provider in ("qwen3_vllm", "mock_qwen3_vllm"):
        print(f"vllm_url     : {os.environ.get('VLLM_OMNI_TTS_URL', '(default)')}")
        print(f"vllm_model   : {os.environ.get('VLLM_OMNI_TTS_MODEL', '(default)')}")
    else:
        print(f"model        : {os.environ.get('QWEN3_TTS_MODEL', '(default)')}")
        print(f"clone_only   : {os.environ.get('N20_TTS_CLONE_ONLY', '0')}")
        print(f"flash_attn   : {_flash_attn_status()} (QWEN3_USE_FLASH_ATTN={os.environ.get('QWEN3_USE_FLASH_ATTN', '0')})")
    print(f"line_cache   : {line_cache_enabled()}")
    print(f"text         : {args.text!r}")
    print()

    manager = TTSManager(device=device)
    init_s, _ = _timed("init", lambda: manager.initialize(provider=provider))
    print(f"initialize   : {init_s:.2f}s")

    entity = _entity_stub(campaign_root, npc_uid, npc_type)
    profile = build_voice_profile_from_entity(entity)
    profile.campaign_root = str(campaign_root)
    if args.provider:
        # NPC YAML may pin provider=qwen3; CLI --provider should drive register + synth.
        profile.provider = None

    voice_s, _ = _timed("voice", lambda: manager.create_voice_from_profile(profile))
    print(f"register_voice: {voice_s:.2f}s")

    cache_key = synthesis_cache_key(npc_uid, args.text, None, None, None)
    results: list[tuple[str, float, str | None, float | None]] = []

    def _run_generate(label: str, text: str, *, use_cache_key: bool = False) -> None:
        def _gen():
            return manager.generate(
                text,
                npc_uid,
                synthesis_key=cache_key if use_cache_key else None,
            )

        elapsed, path = _timed(label, _gen)
        audio_path = Path(path)
        duration = _wav_duration_seconds(audio_path) if audio_path.is_file() else None
        results.append((label, elapsed, str(audio_path), duration))
        rtf = (elapsed / duration) if duration and duration > 0 else None
        rtf_s = f", rtf={rtf:.2f}" if rtf is not None else ""
        dur_s = f", audio={duration:.2f}s" if duration is not None else ""
        print(f"{label:16}: {elapsed:.2f}s{dur_s}{rtf_s} -> {audio_path.name}")

    for index in range(max(1, args.runs)):
        label = "synthesize_1" if index == 0 else f"synthesize_{index + 1}"
        _run_generate(label, args.text, use_cache_key=line_cache_enabled())

    if line_cache_enabled():
        _run_generate("cache_hit", args.text, use_cache_key=True)

    _run_generate("alt_line", args.alt_text, use_cache_key=False)

    print()
    print("=== summary ===")
    synth_times = [elapsed for label, elapsed, _path, _dur in results if label.startswith("synthesize")]
    if synth_times:
        print(f"primary line   : min={min(synth_times):.2f}s max={max(synth_times):.2f}s avg={sum(synth_times) / len(synth_times):.2f}s")
    cache_rows = [elapsed for label, elapsed, _path, _dur in results if label == "cache_hit"]
    if cache_rows:
        print(f"line cache hit : {cache_rows[0]:.2f}s")
    alt_rows = [elapsed for label, elapsed, _path, _dur in results if label == "alt_line"]
    if alt_rows:
        print(f"alternate line : {alt_rows[0]:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
