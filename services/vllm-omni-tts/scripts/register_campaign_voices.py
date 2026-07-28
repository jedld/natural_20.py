#!/usr/bin/env python3
"""Register baked campaign voice samples with a vLLM-Omni TTS server.

Uploads ``assets/voice_samples/<npc_uid>.wav`` (+ optional ``.ref.txt``) to
``POST /v1/audio/voices`` so the webapp can synthesize with ``voice=n20_<uid>``.

Example:
  cd services/vllm-omni-tts
  ./scripts/register_campaign_voices.py ../../user_levels/wild_sheep_chase
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError as exc:
    raise SystemExit("httpx required: pip install httpx") from exc


def _load_dotenv(sidecar_root: Path) -> None:
    env_path = sidecar_root / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _base_url() -> str:
    explicit = os.environ.get("VLLM_OMNI_TTS_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    port = os.environ.get("VLLM_PORT", "8091").strip() or "8091"
    return f"http://127.0.0.1:{port}"


def _voice_prefix() -> str:
    return os.environ.get("VLLM_VOICE_PREFIX", "n20_").strip() or "n20_"


def _consent() -> str:
    return os.environ.get("VLLM_VOICE_CONSENT", "campaign_baked").strip() or "campaign_baked"


def _list_voices(client: httpx.Client, base: str) -> set[str]:
    response = client.get(f"{base}/v1/audio/voices", timeout=30.0)
    response.raise_for_status()
    payload = response.json()
    names: set[str] = set()
    if isinstance(payload, dict):
        for item in payload.get("voices") or payload.get("data") or []:
            if isinstance(item, dict):
                name = item.get("name") or item.get("id")
                if name:
                    names.add(str(name))
            elif isinstance(item, str):
                names.add(item)
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("name"):
                names.add(str(item["name"]))
            elif isinstance(item, str):
                names.add(item)
    return names


def _ref_text(wav_path: Path) -> str:
    sidecar = wav_path.with_suffix(".ref.txt")
    if sidecar.is_file():
        text = sidecar.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "A steady voice for dialogue. Warm, clear, and natural, just as I always speak."


def main() -> int:
    parser = argparse.ArgumentParser(description="Register campaign voice samples with vLLM-Omni")
    parser.add_argument("campaign_root", type=Path, help="Campaign folder (contains assets/voice_samples/)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without uploading")
    parser.add_argument("--force", action="store_true", help="Upload even if voice name already exists")
    args = parser.parse_args()

    sidecar_root = Path(__file__).resolve().parents[1]
    _load_dotenv(sidecar_root)

    campaign_root = args.campaign_root.resolve()
    samples_dir = campaign_root / "assets" / "voice_samples"
    if not samples_dir.is_dir():
        print(f"No voice_samples directory: {samples_dir}", file=sys.stderr)
        return 1

    base = _base_url()
    prefix = _voice_prefix()
    consent = _consent()

    wavs = sorted(samples_dir.glob("*.wav"))
    if not wavs:
        print(f"No WAV files in {samples_dir}")
        return 0

    uploaded = 0
    skipped = 0
    failed = 0

    with httpx.Client(timeout=120.0) as client:
        try:
            existing = _list_voices(client, base)
        except httpx.HTTPError as exc:
            print(f"Cannot reach vLLM-Omni at {base}: {exc}", file=sys.stderr)
            return 1

        for wav_path in wavs:
            voice_name = f"{prefix}{wav_path.stem}"
            if voice_name in existing and not args.force:
                print(f"[skip] {voice_name} (already registered)")
                skipped += 1
                continue

            ref_text = _ref_text(wav_path)
            if args.dry_run:
                print(f"[dry-run] POST /v1/audio/voices name={voice_name} file={wav_path}")
                uploaded += 1
                continue

            try:
                with wav_path.open("rb") as audio_file:
                    response = client.post(
                        f"{base}/v1/audio/voices",
                        data={
                            "consent": consent,
                            "name": voice_name,
                            "ref_text": ref_text,
                        },
                        files={"audio_sample": (wav_path.name, audio_file, "audio/wav")},
                    )
                response.raise_for_status()
                print(f"[ok] {voice_name} <- {wav_path.name}")
                uploaded += 1
                existing.add(voice_name)
            except httpx.HTTPError as exc:
                body = ""
                if getattr(exc, "response", None) is not None:
                    body = exc.response.text[:300]
                print(f"[error] {voice_name}: {exc} {body}", file=sys.stderr)
                failed += 1

    print(f"Done. uploaded={uploaded} skipped={skipped} failed={failed} total={len(wavs)}")
    return 1 if failed and not uploaded else 0


if __name__ == "__main__":
    raise SystemExit(main())
