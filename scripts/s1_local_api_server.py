#!/usr/bin/env python3
"""Serve the local System One-style model with the TypeSafe "System One" wire protocol.

The app itself lives in ``s1_local/server.py`` (importable for tests); this is
the command-line launcher. It speaks the same HTTP contract as
``https://api.typesafe.ai``, so the engine's ``JevProvider`` / ``typesafe_sdk``
client can be pointed at the local model exactly like the hosted JEV:

    # battle "llm" controllers use the local model
    BATTLE_LLM_PROVIDER=jev
    BATTLE_TYPESAFE_BASE_URL=http://127.0.0.1:8902
    BATTLE_TYPESAFE_API_KEY=local        # any value; ignored unless --api-key

    # or the whole engine:
    TYPESAFE_BASE_URL=http://127.0.0.1:8902

Train first, then serve:

    python scripts/train_s1_local.py
    python scripts/s1_local_api_server.py --checkpoint logs/s1_local/model.pt
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from s1_local.server import build_app, load_predictor  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--checkpoint', default='logs/s1_local/model.pt')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=int(os.environ.get('S1_LOCAL_PORT', '8902')))
    ap.add_argument('--api-key', default=os.environ.get('S1_LOCAL_API_KEY'),
                    help='optional shared secret; clients must send it as Bearer')
    ap.add_argument('--device', default=None, help='cuda / cpu (default: auto)')
    ap.add_argument('--temperature', type=float, default=float(os.environ.get('S1_LOCAL_TEMPERATURE', '1.0')),
                    help='softmax temperature (1.0 = the trained calibration)')
    args = ap.parse_args()

    if not Path(args.checkpoint).exists():
        print(f"ERROR: checkpoint not found: {args.checkpoint}\n"
              "Train first: python scripts/train_s1_local.py", file=sys.stderr)
        return 2

    import uvicorn

    predictor = load_predictor(args.checkpoint, device=args.device)
    predictor.meta['temperature'] = args.temperature
    print(f"loaded {args.checkpoint} on {predictor.device} "
          f"(vocab={predictor.tokenizer.vocab_size}, max_options={predictor.max_options})")
    app = build_app(predictor, api_key=args.api_key)
    print(f"s1-local System One server on http://{args.host}:{args.port}")
    print(f"point the engine at it: BATTLE_TYPESAFE_BASE_URL=http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level='info')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
