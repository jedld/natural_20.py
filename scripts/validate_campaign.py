#!/usr/bin/env python3
"""Validate and optionally repair Natural20 campaign YAML."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Natural20 campaign YAML and optionally repair issues with the configured LLM."
    )
    parser.add_argument("campaign", type=Path, help="Campaign directory, e.g. user_levels/my_campaign")
    parser.add_argument("--static-only", action="store_true", help="Skip Session and character loading")
    parser.add_argument("--skip-formatting", action="store_true", help="Skip YAML formatting checks")
    parser.add_argument("--skip-references", action="store_true", help="Skip item/NPC/spell/object reference checks")
    parser.add_argument("--verbose", action="store_true", help="Print engine-load traceback on failure")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON report")
    parser.add_argument("--repair", action="store_true", help="Attempt automated repairs for repairable issues")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write repair proposals to disk (creates backups). Default is dry-run.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use deterministic stub/typo repairs only; do not call the LLM endpoint",
    )
    parser.add_argument("--max-repairs", type=int, default=20, help="Maximum repairs to attempt")
    args = parser.parse_args()

    sys.path.insert(0, str(_repo_root()))

    from natural20.campaign_repair import RepairOptions, proposals_to_json, repair_campaign
    from natural20.campaign_validator import ValidateOptions, validate_campaign

    campaign = args.campaign.expanduser().resolve()
    report = validate_campaign(
        campaign,
        ValidateOptions(
            static_only=args.static_only,
            skip_formatting=args.skip_formatting,
            skip_references=args.skip_references,
            verbose=args.verbose,
        ),
    )

    proposals = []
    if args.repair and report.repairable_issues:
        proposals = repair_campaign(
            campaign,
            report,
            RepairOptions(
                apply=args.apply,
                dry_run=not args.apply,
                use_llm=not args.no_llm,
                max_repairs=args.max_repairs,
            ),
        )

    if args.json:
        payload = {
            "campaign": str(campaign),
            "ok": report.ok(),
            "issues": [issue.to_dict() for issue in report.issues],
            "repairs": proposals_to_json(proposals),
        }
        print(json.dumps(payload, indent=2))
    else:
        report.print()
        if proposals:
            print(f"\nRepair proposals ({len(proposals)}):")
            for proposal in proposals:
                mode = "APPLY" if args.apply else "DRY-RUN"
                print(f"  [{mode}] {proposal.summary}")
            if not args.apply:
                print("\nRe-run with --repair --apply to write these changes.")

    if args.apply and proposals:
        print(f"\nApplied {len(proposals)} repair(s). Re-run validation to confirm.")
        return 0 if report.ok() else 1

    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
