#!/usr/bin/env python3
"""Compare imported battlemap YAML to a hand-authored gold map.

Reports wall IoU, door recall, and occupancy IoU. Does not write campaign files.

Example:

  python scripts/compare_map_import.py \\
      user_levels/death_house/maps/entryway.yml \\
      /tmp/n20_dh_import/yaml/entryway.yml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from natural20.map_import.compare import compare_map_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare imported map YAML against gold occupancy.")
    parser.add_argument("gold", help="Hand-authored map YAML")
    parser.add_argument("generated", help="Importer output YAML")
    parser.add_argument("--json", action="store_true", dest="json_stdout", help="Print JSON only")
    args = parser.parse_args(argv)
    report = compare_map_files(args.gold, args.generated)
    print(json.dumps(report, indent=2))
    if not args.json_stdout:
        print(
            f"wall_iou={report['wall_iou']} occupancy_iou={report['occupancy_iou']} "
            f"door_recall={report['door_recall']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
