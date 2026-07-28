#!/usr/bin/env python3
"""Backward-compatible wrapper around scripts/validate_campaign.py."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.validate_campaign import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
