"""Reference validation for items, spells, NPCs, and objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from natural20.campaign_validator.catalog import CampaignCatalog
from natural20.campaign_validator.report import ValidationReport

SPELL_LIST_FIELDS = (
    "cantrips",
    "prepared_spells",
    "spells_known",
    "spellbook",
    "domain_spells",
)


def validate_catalog_references(
    campaign: Path,
    catalog: CampaignCatalog,
    report: ValidationReport,
) -> None:
    _validate_characters(campaign, catalog, report)
    _validate_npcs(campaign, catalog, report)
    _validate_equipment_packs(campaign, catalog, report)


def _validate_characters(campaign: Path, catalog: CampaignCatalog, report: ValidationReport) -> None:
    characters_dir = campaign / "characters"
    if not characters_dir.is_dir():
        return
    for path in sorted(characters_dir.glob("*.yml")):
        rel = str(path.relative_to(campaign))
        from natural20.campaign_validator.yaml_checks import load_yaml_file

        data = load_yaml_file(path, report, required=False)
        if data is None:
            continue
        label = data.get("name") or path.stem

        for race in _as_list(data.get("race")):
            if not catalog.race_exists(race):
                report.error(
                    f"character {label!r} references unknown race {race!r}",
                    code="missing_race",
                    path=rel,
                    context={"race": race, "character": label},
                    repairable=True,
                )

        classes = data.get("char_class") or data.get("classes")
        for klass in _class_names(classes):
            if not catalog.class_exists(klass):
                report.error(
                    f"character {label!r} references unknown class {klass!r}",
                    code="missing_class",
                    path=rel,
                    context={"class": klass, "character": label},
                    repairable=True,
                )

        background = data.get("background")
        if isinstance(background, str) and background and not catalog.background_exists(background):
            report.error(
                f"character {label!r} references unknown background {background!r}",
                code="missing_background",
                path=rel,
                context={"background": background, "character": label},
                repairable=True,
            )

        for field in SPELL_LIST_FIELDS:
            for spell in _as_list(data.get(field)):
                if not catalog.spell_exists(spell):
                    suggestions = catalog.suggest_spell(spell)
                    report.error(
                        f"character {label!r} references unknown spell {spell!r} in {field}",
                        code="missing_spell",
                        path=rel,
                        context={
                            "spell": spell,
                            "field": field,
                            "character": label,
                            "suggestions": suggestions,
                        },
                        repairable=True,
                    )

        for item_ref in _inventory_item_refs(data):
            if not catalog.item_exists(item_ref):
                suggestions = catalog.suggest_item(item_ref)
                report.error(
                    f"character {label!r} references unknown item {item_ref!r}",
                    code="missing_item",
                    path=rel,
                    context={"item": item_ref, "character": label, "suggestions": suggestions},
                    repairable=True,
                )


def _validate_npcs(campaign: Path, catalog: CampaignCatalog, report: ValidationReport) -> None:
    npcs_dir = campaign / "npcs"
    if not npcs_dir.is_dir():
        return
    for path in sorted(npcs_dir.glob("*.yml")):
        rel = str(path.relative_to(campaign))
        from natural20.campaign_validator.yaml_checks import load_yaml_file

        data = load_yaml_file(path, report, required=False)
        if data is None:
            continue
        label = path.stem
        for race in _as_list(data.get("race")):
            if not catalog.race_exists(race):
                report.warning(
                    f"npc {label!r} references unknown race {race!r}",
                    code="missing_race",
                    path=rel,
                    context={"race": race, "npc": label},
                    repairable=True,
                )
        for item_ref in _inventory_item_refs(data):
            if not catalog.item_exists(item_ref):
                suggestions = catalog.suggest_item(item_ref)
                report.warning(
                    f"npc {label!r} references unknown item {item_ref!r}",
                    code="missing_item",
                    path=rel,
                    context={"item": item_ref, "npc": label, "suggestions": suggestions},
                    repairable=True,
                )


def _validate_equipment_packs(campaign: Path, catalog: CampaignCatalog, report: ValidationReport) -> None:
    packs = catalog.equipment_packs
    for pack_name, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        for entry in pack.get("contents", []) or []:
            if not isinstance(entry, dict):
                continue
            item_ref = entry.get("type") or entry.get("item") or entry.get("name")
            if not item_ref or catalog.item_exists(item_ref):
                continue
            suggestions = catalog.suggest_item(item_ref)
            report.error(
                f"equipment pack {pack_name!r} references unknown item {item_ref!r}",
                code="missing_item",
                path="items/equipment_packs.yml",
                context={"item": item_ref, "pack": pack_name, "suggestions": suggestions},
                repairable=True,
            )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, dict):
        return [str(key) for key in value.keys()]
    return []


def _class_names(classes: Any) -> list[str]:
    if classes is None:
        return []
    if isinstance(classes, str):
        return [classes]
    if isinstance(classes, list):
        return [str(item) for item in classes if item is not None]
    if isinstance(classes, dict):
        return [str(key) for key in classes.keys()]
    return []


def _inventory_item_refs(data: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for item in data.get("inventory", []) or []:
        if isinstance(item, str):
            refs.append(item)
            continue
        if not isinstance(item, dict):
            continue
        item_ref = item.get("type") or item.get("item")
        if item_ref:
            refs.append(str(item_ref))
        elif item.get("name"):
            refs.append(str(item["name"]))
    for item in data.get("equipped", []) or []:
        if isinstance(item, str):
            refs.append(item)
    return refs
