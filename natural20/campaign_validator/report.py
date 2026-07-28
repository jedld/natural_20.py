"""Validation report types for campaign validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationIssue:
    """A single validation finding."""

    message: str
    severity: Severity = Severity.ERROR
    code: str = "validation"
    path: str | None = None
    line: int | None = None
    context: dict[str, Any] = field(default_factory=dict)
    repairable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "severity": self.severity.value,
            "code": self.code,
            "path": self.path,
            "line": self.line,
            "context": self.context,
            "repairable": self.repairable,
        }


@dataclass
class ValidationReport:
    """Aggregated validation results."""

    issues: list[ValidationIssue] = field(default_factory=list)

    def error(
        self,
        message: str,
        *,
        code: str = "validation",
        path: str | None = None,
        line: int | None = None,
        context: dict[str, Any] | None = None,
        repairable: bool = False,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                message=message,
                severity=Severity.ERROR,
                code=code,
                path=path,
                line=line,
                context=context or {},
                repairable=repairable,
            )
        )

    def warning(
        self,
        message: str,
        *,
        code: str = "validation",
        path: str | None = None,
        line: int | None = None,
        context: dict[str, Any] | None = None,
        repairable: bool = False,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                message=message,
                severity=Severity.WARNING,
                code=code,
                path=path,
                line=line,
                context=context or {},
                repairable=repairable,
            )
        )

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == Severity.WARNING]

    @property
    def repairable_issues(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.repairable]

    def ok(self) -> bool:
        return not self.errors

    def print(self) -> None:
        for issue in self.issues:
            prefix = "ERROR" if issue.severity == Severity.ERROR else "WARN "
            location = ""
            if issue.path:
                location = issue.path
                if issue.line is not None:
                    location += f":{issue.line}"
                location = f" ({location})"
            print(f"{prefix}:{location} {issue.message}")
        print(
            f"\nCampaign validation: {len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s)"
        )
