"""Structured targeting validation issues for actions, spells, and items.

Tile targeting and ``/target`` previews should surface *why* a candidate is
invalid.  Callers record :class:`TargetValidationIssue` entries (i18n keys plus
optional interpolation params).  The web layer serializes them via
:func:`validation_response_payload`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

try:
    import i18n
except ImportError:  # pragma: no cover - optional in some tooling contexts
    i18n = None  # type: ignore[assignment]


@dataclass(frozen=True)
class TargetValidationIssue:
    """One targeting failure with an i18n key and optional template params."""

    key: str
    params: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    def resolve_message(self) -> str:
        if self.message:
            return self.message
        if i18n is not None:
            try:
                return str(i18n.t(self.key, **self.params))
            except Exception:
                pass
        if self.params:
            param_text = ", ".join(f"{k}={v}" for k, v in self.params.items())
            return f"{self.key} ({param_text})"
        return self.key

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "params": dict(self.params),
            "message": self.resolve_message(),
        }


def issue(key: str, /, **params: Any) -> TargetValidationIssue:
    return TargetValidationIssue(key=key, params=params)


def clear_validation(owner: Any) -> None:
    owner.errors = []
    owner.validation_issues = []


def add_validation_issue(owner: Any, entry: TargetValidationIssue | str, /, **params: Any) -> None:
    if not hasattr(owner, "validation_issues"):
        owner.validation_issues = []
    if isinstance(entry, str):
        entry = issue(entry, **params)
    owner.validation_issues.append(entry)
    owner.errors.append(entry.key)


def extend_validation_issues(owner: Any, issues: Iterable[TargetValidationIssue]) -> None:
    for entry in issues:
        add_validation_issue(owner, entry)


def normalize_error_entry(entry: str | Mapping[str, Any] | TargetValidationIssue) -> dict[str, Any]:
    if isinstance(entry, TargetValidationIssue):
        return entry.to_dict()
    if isinstance(entry, str):
        return issue(entry).to_dict()
    key = str(entry.get("key") or entry.get("error") or "")
    params = dict(entry.get("params") or {})
    message = entry.get("message")
    resolved = TargetValidationIssue(key=key, params=params, message=message)
    return resolved.to_dict()


def validation_response_payload(owner: Any) -> dict[str, Any]:
    """JSON-friendly validation block for Flask ``jsonify`` responses."""
    issues = list(getattr(owner, "validation_issues", []) or [])
    if not issues:
        legacy = list(getattr(owner, "errors", []) or [])
        issues = [issue(key) if isinstance(key, str) else issue(str(key)) for key in legacy]
    details = [entry.to_dict() if isinstance(entry, TargetValidationIssue) else normalize_error_entry(entry)
               for entry in issues]
    keys = [detail["key"] for detail in details]
    messages = [detail["message"] for detail in details]
    return {
        "errors": keys,
        "error_details": details,
        "error_messages": messages,
        "primary_error": messages[0] if messages else None,
    }


def has_validation_failures(owner: Any) -> bool:
    if getattr(owner, "validation_issues", None):
        return bool(owner.validation_issues)
    return bool(getattr(owner, "errors", None))


def _distance_ft_between(battle_map, entity_a, entity_b) -> float | None:
    if battle_map is None or entity_a is None or entity_b is None:
        return None
    try:
        return battle_map.distance(entity_a, entity_b) * battle_map.feet_per_grid
    except Exception:
        return None


def evaluate_entity_target(
    source,
    target,
    battle,
    *,
    max_range_ft: float | None = None,
    require_ally: bool = False,
    require_enemy: bool = False,
    allow_self: bool = False,
    require_hearing: bool = False,
    require_same_map: bool = True,
) -> list[TargetValidationIssue]:
    """Shared creature-target checks used by actions and spells."""
    issues: list[TargetValidationIssue] = []

    if target is None:
        issues.append(issue("validation.targeting.required"))
        return issues

    if target == source and not allow_self:
        issues.append(issue("validation.targeting.self"))
        return issues

    if require_hearing:
        statuses = getattr(target, "statuses", []) or []
        if "deafened" in statuses:
            issues.append(issue("validation.targeting.deafened"))

    if battle is not None:
        if require_ally and not battle.allies(source, target):
            issues.append(issue("validation.targeting.not_ally"))
        if require_enemy and not battle.opposing(source, target):
            issues.append(issue("validation.targeting.not_enemy"))

        if require_same_map:
            target_map = battle.map_for(target)
            caster_map = battle.map_for(source)
            if target_map is None or caster_map is None:
                issues.append(issue("validation.targeting.unavailable"))
            elif target_map is not caster_map:
                issues.append(issue("validation.targeting.different_map"))

        if max_range_ft is not None:
            caster_map = battle.map_for(source) if battle is not None else None
            distance_ft = _distance_ft_between(caster_map, source, target)
            if distance_ft is not None and distance_ft > max_range_ft:
                issues.append(
                    issue(
                        "validation.targeting.out_of_range",
                        range_ft=int(max_range_ft),
                        distance_ft=int(distance_ft),
                    )
                )

    return issues


def evaluate_coordinate_target(
    source,
    target,
    battle_map,
    *,
    max_range_ft: float | None = None,
    require_empty: bool = False,
    require_visible: bool = False,
) -> list[TargetValidationIssue]:
    """Shared map-square targeting checks."""
    issues: list[TargetValidationIssue] = []

    if target is None:
        issues.append(issue("validation.targeting.required"))
        return issues

    if not (isinstance(target, (list, tuple)) and len(target) >= 2):
        issues.append(issue("validation.targeting.invalid_position"))
        return issues

    x, y = int(target[0]), int(target[1])
    if battle_map is None:
        issues.append(issue("validation.targeting.unavailable"))
        return issues

    if require_empty and battle_map.entity_at(x, y) is not None:
        issues.append(issue("validation.targeting.occupied"))

    if require_visible:
        try:
            if not battle_map.can_see(source, (x, y)):
                issues.append(issue("validation.targeting.not_visible"))
        except Exception:
            issues.append(issue("validation.targeting.not_visible"))

    if max_range_ft is not None and source is not None:
        try:
            distance_ft = battle_map.distance_to_square(source, x, y) * battle_map.feet_per_grid
        except Exception:
            distance_ft = None
        if distance_ft is not None and distance_ft > max_range_ft:
            issues.append(
                issue(
                    "validation.targeting.out_of_range",
                    range_ft=int(max_range_ft),
                    distance_ft=int(distance_ft),
                )
            )

    return issues


def resolve_battle_for_validation(battle_map, source=None, battle=None):
    if battle is not None:
        return battle
    if battle_map is not None:
        attached = getattr(battle_map, 'battle', None)
        if attached is not None:
            return attached
    session = None
    if battle_map is not None:
        session = getattr(battle_map, 'session', None)
    if session is None and source is not None:
        session = getattr(source, 'session', None)
    if session is not None:
        return getattr(session, 'current_battle', None)
    return None


def evaluate_bardic_inspiration_target(source, target, battle) -> list[TargetValidationIssue]:
    return evaluate_entity_target(
        source,
        target,
        battle,
        max_range_ft=60,
        require_ally=True,
        require_hearing=True,
    )
