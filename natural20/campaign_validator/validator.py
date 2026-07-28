"""Campaign validation orchestration."""

from __future__ import annotations

import os
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from natural20.campaign_validator.catalog import CampaignCatalog
from natural20.campaign_validator.reference_checks import validate_catalog_references
from natural20.campaign_validator.report import ValidationReport
from natural20.campaign_validator.static_checks import validate_static_structure
from natural20.campaign_validator.yaml_checks import validate_yaml_files


@dataclass
class ValidateOptions:
    static_only: bool = False
    skip_formatting: bool = False
    skip_references: bool = False
    verbose: bool = False


def validate_campaign(campaign: Path | str, options: ValidateOptions | None = None) -> ValidationReport:
    """Validate a campaign directory and return a structured report."""
    opts = options or ValidateOptions()
    campaign_path = Path(campaign).expanduser().resolve()
    report = ValidationReport()

    if not campaign_path.is_dir():
        report.error(f"campaign directory does not exist: {campaign_path}")
        return report

    if not opts.skip_formatting:
        validate_yaml_files(campaign_path, report)

    catalog = CampaignCatalog(campaign_path)
    validate_static_structure(campaign_path, catalog, report)

    if not opts.skip_references:
        validate_catalog_references(campaign_path, catalog, report)

    if not opts.static_only and report.ok():
        _run_engine_load(campaign_path, report, opts.verbose)

    return report


def _repo_root() -> Path:
    import natural20 as n20

    return Path(n20.__file__).resolve().parent.parent


def _run_engine_load(campaign: Path, report: ValidationReport, verbose: bool) -> None:
    old_cwd = Path.cwd()
    try:
        # NPC fallback paths in legacy loaders are cwd-relative.
        os.chdir(_repo_root())
        from natural20.session import Session

        with redirect_stdout(StringIO()):
            session = Session(root_path=str(campaign))
            characters_dir = campaign / "characters"
            if characters_dir.is_dir():
                session.load_characters()
        print(f"Loaded {len(session.maps)} map(s) through natural20.session.Session")
    except Exception as exc:
        report.error(f"Natural20 engine load failed: {type(exc).__name__}: {exc}")
        if verbose:
            traceback.print_exc()
    finally:
        os.chdir(old_cwd)
