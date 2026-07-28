#!/usr/bin/env python3
"""Write .ref.txt sidecars for existing baked voice samples (fixes clone ref_text mismatch)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webapp.tts.voice_baking import bake_sample_text, save_baked_ref_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill voice sample ref-text sidecars")
    parser.add_argument("campaign_root", type=Path)
    args = parser.parse_args()

    samples_dir = args.campaign_root.resolve() / "assets" / "voice_samples"
    if not samples_dir.is_dir():
        print(f"No voice_samples directory: {samples_dir}", file=sys.stderr)
        return 1

    ref_text = bake_sample_text()
    written = 0
    for wav in sorted(samples_dir.glob("*.wav")):
        uid = wav.stem
        save_baked_ref_text(str(args.campaign_root.resolve()), uid, ref_text)
        written += 1
        print(f"[ref] {uid}.ref.txt")
    print(f"Done. wrote={written} ref_text={ref_text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
