"""YAML syntax and formatting checks."""

from __future__ import annotations

from pathlib import Path

import yaml

from natural20.campaign_validator.report import ValidationReport


def validate_yaml_files(campaign: Path, report: ValidationReport) -> dict[Path, dict]:
    """Parse every YAML file under the campaign and return loaded documents."""
    documents: dict[Path, dict] = {}
    for path in sorted(campaign.rglob("*.yml")):
        rel = str(path.relative_to(campaign))
        text = _read_text(path, rel, report)
        if text is None:
            continue
        _check_formatting(path, rel, text, report)
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            line = getattr(getattr(exc, "problem_mark", None), "line", None)
            if line is not None:
                line += 1
            report.error(
                f"cannot parse {rel}: {exc}",
                code="yaml_syntax",
                path=rel,
                line=line,
                repairable=True,
            )
            continue
        if data is None:
            report.warning(f"{rel} is empty", code="yaml_empty", path=rel)
            continue
        if not isinstance(data, dict):
            report.error(
                f"{rel} must contain a YAML mapping at the document root",
                code="yaml_structure",
                path=rel,
            )
            continue
        documents[path] = data
    return documents


def load_yaml_file(path: Path, report: ValidationReport, *, required: bool = True) -> dict | None:
    rel = path.name
    if not path.is_file():
        if required:
            report.error(f"missing YAML file: {path}", code="missing_file", path=rel)
        return None
    text = _read_text(path, rel, report)
    if text is None:
        return None
    _check_formatting(path, rel, text, report)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        line = getattr(getattr(exc, "problem_mark", None), "line", None)
        if line is not None:
            line += 1
        report.error(
            f"cannot parse {rel}: {exc}",
            code="yaml_syntax",
            path=rel,
            line=line,
            repairable=True,
        )
        return None
    if not isinstance(data, dict):
        report.error(
            f"{rel} must contain a YAML mapping at the document root",
            code="yaml_structure",
            path=rel,
        )
        return None
    return data


def _read_text(path: Path, rel: str, report: ValidationReport) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        report.error(f"cannot read {rel}: {exc}", code="io_error", path=rel)
        return None


def _check_formatting(path: Path, rel: str, text: str, report: ValidationReport) -> None:
    if "\t" in text:
        report.warning(
            f"{rel} contains tab characters; YAML style prefers spaces",
            code="yaml_format_tabs",
            path=rel,
            repairable=True,
        )
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.rstrip() != line:
            report.warning(
                f"{rel}:{line_no} has trailing whitespace",
                code="yaml_format_trailing_ws",
                path=rel,
                line=line_no,
                repairable=True,
            )
    if text and not text.endswith("\n"):
        report.warning(
            f"{rel} does not end with a newline",
            code="yaml_format_final_newline",
            path=rel,
            repairable=True,
        )
