"""Campaign resource catalog for reference validation."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from natural20.yaml_loader import load_campaign_yaml, templates_root


def _stem_index(folder: Path) -> dict[str, str]:
    if not folder.is_dir():
        return {}
    index: dict[str, str] = {}
    for path in folder.glob("*.yml"):
        stem = path.stem
        index[stem.lower()] = stem
    return index


class CampaignCatalog:
    """Merged view of campaign-local and bundled template resources."""

    ITEM_FILES = ("weapons", "equipment", "magic_items", "objects", "spells", "equipment_packs")

    def __init__(self, campaign: Path, templates: Path | None = None) -> None:
        self.campaign = campaign.expanduser().resolve()
        self.templates = (templates or templates_root()).resolve()
        self.weapons = self._merge_item_file("weapons")
        self.equipment = self._merge_item_file("equipment")
        self.magic_items = self._merge_item_file("magic_items")
        self.objects = self._merge_item_file("objects")
        self.spells = self._merge_item_file("spells")
        self.equipment_packs = self._merge_item_file("equipment_packs")
        self.npcs = self._merge_stems("npcs")
        self.races = self._merge_stems("races")
        self.char_classes = self._merge_stems("char_classes")
        self.backgrounds = self._merge_stems("backgrounds")
        self._item_alias_index = self._build_item_alias_index()

    def _merge_item_file(self, name: str) -> dict[str, Any]:
        try:
            data = load_campaign_yaml(self.campaign, "items", name)
        except FileNotFoundError:
            return {}
        return data if isinstance(data, dict) else {}

    def _merge_stems(self, category: str) -> dict[str, str]:
        merged: dict[str, str] = {}
        for root in (self.templates, self.campaign):
            merged.update(_stem_index(root / category))
        return merged

    def _build_item_alias_index(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for catalog in (self.weapons, self.equipment, self.magic_items, self.objects, self.equipment_packs):
            for key, entry in catalog.items():
                aliases[key.lower()] = key
                if isinstance(entry, dict):
                    for field in ("name", "label"):
                        label = entry.get(field)
                        if isinstance(label, str) and label.strip():
                            aliases[label.strip().lower()] = key
        return aliases

    def resolve_item_id(self, raw: str) -> str | None:
        if not raw:
            return None
        key = raw.strip()
        lowered = key.lower()
        if lowered in self._item_alias_index:
            return self._item_alias_index[lowered]
        if key in self.weapons or key in self.equipment or key in self.magic_items or key in self.objects or key in self.equipment_packs:
            return key
        return None

    def item_exists(self, raw: str) -> bool:
        return self.resolve_item_id(raw) is not None

    def spell_exists(self, raw: str) -> bool:
        return bool(raw) and raw in self.spells

    def object_exists(self, raw: str) -> bool:
        return bool(raw) and raw in self.objects

    def npc_exists(self, raw: str) -> bool:
        if not raw:
            return False
        return raw.lower() in self.npcs

    def race_exists(self, raw: str) -> bool:
        if not raw:
            return False
        return raw.lower() in self.races

    def class_exists(self, raw: str) -> bool:
        if not raw:
            return False
        return raw.lower() in self.char_classes

    def background_exists(self, raw: str) -> bool:
        if not raw:
            return False
        return raw.lower() in self.backgrounds

    def suggest_item(self, raw: str, *, limit: int = 5) -> list[str]:
        choices = sorted(set(self._item_alias_index.values()))
        return difflib.get_close_matches(raw, choices, n=limit, cutoff=0.6)

    def suggest_spell(self, raw: str, *, limit: int = 5) -> list[str]:
        return difflib.get_close_matches(raw, sorted(self.spells), n=limit, cutoff=0.6)

    def suggest_npc(self, raw: str, *, limit: int = 5) -> list[str]:
        choices = sorted(set(self.npcs.values()))
        return difflib.get_close_matches(raw, choices, n=limit, cutoff=0.6)

    def suggest_object(self, raw: str, *, limit: int = 5) -> list[str]:
        return difflib.get_close_matches(raw, sorted(self.objects), n=limit, cutoff=0.6)
