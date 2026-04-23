#!/usr/bin/env python3
"""Import D&D Beyond characters into natural20.py YAML format.

This module exposes :class:`BeyondImporter`, which converts a JSON payload from
the public D&D Beyond character API (or a saved JSON file) into the YAML schema
consumed by :class:`natural20.player_character.PlayerCharacter`.

The importer focuses on producing data the engine actually reads — race /
subrace, stats, multiclass levels, skill / tool / language proficiencies,
expertise, weapon and armor proficiencies, resistances, prepared spells,
cantrips, spellbook contents, equipped gear and inventory.  Unknown items and
spells are filtered (with warnings) so the resulting YAML can be loaded
without surprising lookup failures.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

try:  # ``requests`` is only needed when fetching from the network.
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

_STAT_IDS: Dict[int, str] = {1: "str", 2: "dex", 3: "con", 4: "int", 5: "wis", 6: "cha"}

_ALIGNMENT_MAP: Dict[int, str] = {
    1: "lawful_good",
    2: "neutral_good",
    3: "chaotic_good",
    4: "lawful_neutral",
    5: "true_neutral",
    6: "chaotic_neutral",
    7: "lawful_evil",
    8: "neutral_evil",
    9: "chaotic_evil",
}

_RACE_OVERRIDES: Dict[str, Tuple[str, Optional[str]]] = {
    "high elf": ("elf", "high_elf"),
    "wood elf": ("elf", "wood_elf"),
    "dark elf": ("elf", "dark_elf"),
    "drow": ("elf", "dark_elf"),
    "hill dwarf": ("dwarf", "hill_dwarf"),
    "mountain dwarf": ("dwarf", "mountain_dwarf"),
    "lightfoot halfling": ("halfling", "lightfoot"),
    "stout halfling": ("halfling", "stout"),
    "rock gnome": ("gnome", "rock_gnome"),
    "forest gnome": ("gnome", "forest_gnome"),
}

_SUBCLASS_KEY_BY_CLASS: Dict[str, str] = {
    "barbarian": "primal_path",
    "bard": "bard_college",
    "cleric": "divine_domain",
    "druid": "druidic_circle",
    "fighter": "martial_archetype",
    "monk": "monastic_tradition",
    "paladin": "sacred_oath",
    "ranger": "ranger_archetype",
    "rogue": "roguish_archetype",
    "sorcerer": "sorcerous_origin",
    "warlock": "otherworldly_patron",
    "wizard": "arcane_tradition",
}

_FULL_CASTER_SLOTS: List[List[int]] = [
    [],
    [2],
    [3],
    [4, 2],
    [4, 3],
    [4, 3, 2],
    [4, 3, 3],
    [4, 3, 3, 1],
    [4, 3, 3, 2],
    [4, 3, 3, 3, 1],
    [4, 3, 3, 3, 2],
    [4, 3, 3, 3, 2, 1],
    [4, 3, 3, 3, 2, 1],
    [4, 3, 3, 3, 2, 1, 1],
    [4, 3, 3, 3, 2, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 2, 1, 1],
]

_FULL_CASTERS = {"bard", "cleric", "druid", "sorcerer", "wizard"}
_HALF_CASTERS = {"paladin", "ranger"}

_WARLOCK_PACT_SLOTS: Dict[int, Tuple[int, int]] = {
    1: (1, 1), 2: (2, 1), 3: (2, 2), 4: (2, 2), 5: (2, 3), 6: (2, 3),
    7: (2, 4), 8: (2, 4), 9: (2, 5), 10: (2, 5), 11: (3, 5), 12: (3, 5),
    13: (3, 5), 14: (3, 5), 15: (3, 5), 16: (3, 5), 17: (4, 5), 18: (4, 5),
    19: (4, 5), 20: (4, 5),
}

_ABILITY_FULL: Dict[str, str] = {
    "str": "strength",
    "dex": "dexterity",
    "con": "constitution",
    "int": "intelligence",
    "wis": "wisdom",
    "cha": "charisma",
}

_SKILL_NAMES: Set[str] = {
    "acrobatics", "animal_handling", "arcana", "athletics", "deception",
    "history", "insight", "intimidation", "investigation", "medicine",
    "nature", "perception", "performance", "persuasion", "religion",
    "sleight_of_hand", "stealth", "survival",
}

_TOOL_NAMES: Set[str] = {
    "thieves_tools", "alchemists_supplies", "brewers_supplies",
    "calligraphers_supplies", "carpenters_tools", "cartographers_tools",
    "cobblers_tools", "cooks_utensils", "glassblowers_tools",
    "jewelers_tools", "leatherworkers_tools", "masons_tools",
    "painters_supplies", "potters_tools", "smiths_tools",
    "tinkers_tools", "weavers_tools", "woodcarvers_tools",
    "disguise_kit", "forgery_kit", "herbalism_kit", "navigators_tools",
    "poisoners_kit", "drum", "flute", "lute", "lyre", "horn", "pan_flute",
    "shawm", "viol", "bagpipes", "dulcimer",
}

_TOOL_ALIASES: Dict[str, str] = {
    "thieve_s_tools": "thieves_tools",
    "alchemist_s_supplies": "alchemists_supplies",
    "brewer_s_supplies": "brewers_supplies",
    "calligrapher_s_supplies": "calligraphers_supplies",
    "carpenter_s_tools": "carpenters_tools",
    "cartographer_s_tools": "cartographers_tools",
    "cobbler_s_tools": "cobblers_tools",
    "cook_s_utensils": "cooks_utensils",
    "glassblower_s_tools": "glassblowers_tools",
    "jeweler_s_tools": "jewelers_tools",
    "leatherworker_s_tools": "leatherworkers_tools",
    "mason_s_tools": "masons_tools",
    "painter_s_supplies": "painters_supplies",
    "potter_s_tools": "potters_tools",
    "smith_s_tools": "smiths_tools",
    "tinker_s_tools": "tinkers_tools",
    "weaver_s_tools": "weavers_tools",
    "woodcarver_s_tools": "woodcarvers_tools",
    "navigator_s_tools": "navigators_tools",
    "poisoner_s_kit": "poisoners_kit",
}

_WEAPON_PROF_NAMES: Set[str] = {
    "simple_weapons", "martial_weapons",
    "light_armor", "medium_armor", "heavy_armor", "shields",
    "battleaxe", "dagger", "quarterstaff", "sling", "dart", "greatclub",
    "hand_crossbow", "handaxe", "javelin", "heavy_crossbow", "light_crossbow",
    "light_hammer", "longbow", "longsword", "rapier", "scimitar",
    "shortsword", "shortbow", "spear", "warhammer",
    "simple", "martial",
}

_WEAPON_PROF_ALIASES: Dict[str, str] = {
    "simple_weapons": "simple",
    "martial_weapons": "martial",
}

# Item name overrides for D&D Beyond -> engine canonical IDs.  Slugged.
_ITEM_ALIASES: Dict[str, str] = {
    "potion_of_healing": "healing_potion",
    "healer_s_kit": "healers_kit",
    "thieve_s_tools": "thieves_tools",
    "holy_symbol_amulet": "holy_symbol",
    "crossbow_bolts": "bolts",
}

# Spell name aliases (DDB -> engine canonical).  Both keys/values are slugged.
_SPELL_ALIASES: Dict[str, str] = {
    "fire_bolt": "firebolt",
}

_ITEM_CACHE: Optional[Set[str]] = None
_SPELL_CACHE: Optional[Set[str]] = None


def _slug(value: Any) -> str:
    """Convert an arbitrary display string into a snake_case identifier."""
    if value is None:
        return ""
    s = re.sub(r"['\u2019]", "", str(value).lower())
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def _load_known_items() -> Set[str]:
    global _ITEM_CACHE
    if _ITEM_CACHE is not None:
        return _ITEM_CACHE
    items: Set[str] = set()
    base = _templates_dir() / "items"
    for name in ("weapons.yml", "equipment.yml", "objects.yml"):
        path = base / name
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            items.update(data.keys())
    _ITEM_CACHE = items
    return items


def _load_known_spells() -> Set[str]:
    global _SPELL_CACHE
    if _SPELL_CACHE is not None:
        return _SPELL_CACHE
    path = _templates_dir() / "items" / "spells.yml"
    spells: Set[str] = set()
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text()) or {}
            if isinstance(data, dict):
                spells.update(data.keys())
        except yaml.YAMLError:
            pass
    _SPELL_CACHE = spells
    return spells


def _normalize_tool(slug: str) -> str:
    return _TOOL_ALIASES.get(slug, slug)


def _normalize_weapon_prof(slug: str) -> str:
    return _WEAPON_PROF_ALIASES.get(slug, slug)


def _normalize_item(slug: str) -> str:
    return _ITEM_ALIASES.get(slug, slug)


class BeyondImporter:
    """Convert D&D Beyond character payloads to natural20.py YAML."""

    DEFAULT_API = "https://character-service.dndbeyond.com/character/v5/character"

    def __init__(self, *, base_url: Optional[str] = None,
                 user_agent: str = "natural20.py-importer/1.0",
                 strict: bool = False):
        self.base_url = base_url or self.DEFAULT_API
        self.user_agent = user_agent
        self.strict = strict
        self.warnings: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_character(self, character_id: int,
                        cobalt_token: Optional[str] = None,
                        timeout: float = 15.0) -> Dict[str, Any]:
        if requests is None:
            raise RuntimeError("requests is required for network fetches")
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        cookies = {"CobaltSession": cobalt_token} if cobalt_token else None
        url = f"{self.base_url}/{character_id}"
        response = requests.get(url, headers=headers, cookies=cookies,
                                timeout=timeout)
        response.raise_for_status()
        body = response.json()
        return body.get("data", body)

    def load_character(self, source: Any) -> Dict[str, Any]:
        if isinstance(source, dict):
            return source.get("data", source)
        if hasattr(source, "read"):
            data = json.load(source)
        else:
            data = json.loads(Path(source).read_text())
        return data.get("data", data)

    def import_character(self, character_id: Optional[int] = None,
                         output_path: Optional[str] = None,
                         input_path: Optional[str] = None,
                         cobalt_token: Optional[str] = None) -> str:
        if input_path:
            data = self.load_character(input_path)
        else:
            if character_id is None:
                raise ValueError("character_id or input_path is required")
            data = self.fetch_character(character_id, cobalt_token=cobalt_token)
        yaml_data = self.convert_to_yaml(data)
        text = yaml.dump(yaml_data, sort_keys=False, default_flow_style=False,
                         allow_unicode=True)
        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text)
        return text

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------
    def convert_to_yaml(self, character_data: Dict[str, Any]) -> Dict[str, Any]:
        self.warnings = []
        modifiers = self._iter_modifiers(character_data)

        race, subrace = self._extract_race(character_data)
        classes_map, total_level, subclass_fields = self._extract_classes(
            character_data)
        ability = self._extract_ability_scores(character_data, modifiers)
        max_hp, current_hp, temp_hp = self._extract_hit_points(
            character_data, ability.get("con", 10), total_level)

        skills = self._extract_modifiers_of_type(
            modifiers, "proficiency", filter_set=_SKILL_NAMES)
        tools = self._extract_modifiers_of_type(
            modifiers, "proficiency", filter_set=_TOOL_NAMES,
            transform=_normalize_tool)
        weapon_profs = self._extract_modifiers_of_type(
            modifiers, "proficiency", filter_set=_WEAPON_PROF_NAMES,
            transform=_normalize_weapon_prof)
        save_profs = self._extract_save_proficiencies(modifiers)
        languages = self._extract_modifiers_of_type(modifiers, "language")
        expertise = self._extract_modifiers_of_type(
            modifiers, "expertise", filter_set=_SKILL_NAMES | _TOOL_NAMES)
        resistances = self._extract_modifiers_of_type(modifiers, "resistance")
        feats = sorted({_slug((f.get("definition") or {}).get("name") or "")
                        for f in character_data.get("feats", []) or []
                        if f.get("definition")})
        feats = [f for f in feats if f]

        equipped_items, inventory = self._extract_inventory(character_data)
        cantrips, prepared, spellbook = self._extract_spells(
            character_data, classes_map)
        spell_slots = self._compute_spell_slots(classes_map, subclass_fields)

        name = character_data.get("name") or "Unnamed"
        token_letter = (str(name).strip()[:1] or "P").upper()

        yaml_data: Dict[str, Any] = {
            "name": name,
            "race": race,
        }
        if subrace:
            yaml_data["subrace"] = subrace
        gender = character_data.get("gender")
        if gender:
            yaml_data["gender"] = gender
        pronoun = self._extract_pronoun(character_data)
        if pronoun:
            yaml_data["pronoun"] = pronoun

        yaml_data["classes"] = classes_map
        yaml_data["level"] = total_level
        yaml_data["hit_die"] = "inherit"
        yaml_data["max_hp"] = max_hp
        yaml_data["hp"] = current_hp
        if temp_hp:
            yaml_data["temporary_hp"] = temp_hp
        yaml_data["ability"] = ability

        for klass, sub in subclass_fields.items():
            field = _SUBCLASS_KEY_BY_CLASS.get(klass)
            if field and sub:
                yaml_data[field] = sub

        if save_profs:
            yaml_data["saving_throw_proficiencies"] = save_profs
        if skills:
            yaml_data["skills"] = sorted(skills)
        if expertise:
            yaml_data["expertise"] = sorted(expertise)
        if tools:
            yaml_data["tools"] = sorted(tools)
        if weapon_profs:
            yaml_data["weapon_proficiencies"] = sorted(weapon_profs)
        if languages:
            yaml_data["languages"] = sorted({_slug(l) for l in languages})
        if resistances:
            yaml_data["resistances"] = sorted({_slug(r) for r in resistances})
        if feats:
            yaml_data["feats"] = feats

        if cantrips:
            yaml_data["cantrips"] = cantrips
        if prepared:
            yaml_data["prepared_spells"] = prepared
        if spellbook:
            yaml_data["spellbook"] = spellbook
        if spell_slots:
            yaml_data["spell_slots"] = spell_slots

        background = (character_data.get("background") or {}).get("definition") or {}
        if background.get("name"):
            yaml_data["background"] = _slug(background["name"])

        yaml_data["equipped"] = equipped_items
        yaml_data["inventory"] = inventory
        yaml_data["token"] = [token_letter]
        yaml_data["alignment"] = _ALIGNMENT_MAP.get(
            character_data.get("alignmentId") or 5, "true_neutral")
        yaml_data["group"] = "a"
        if character_data.get("id") is not None:
            yaml_data["entity_uid"] = f"ddb-{character_data['id']}"

        return yaml_data

    # ------------------------------------------------------------------
    # Section extractors
    # ------------------------------------------------------------------
    def _extract_race(self, data: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        race_obj = data.get("race") or {}
        full = (race_obj.get("fullName") or race_obj.get("baseName") or "").strip()
        key = full.lower()
        if key in _RACE_OVERRIDES:
            return _RACE_OVERRIDES[key]
        base = race_obj.get("baseRaceName") or race_obj.get("baseName") or full
        sub_short = race_obj.get("subRaceShortName")
        race = _slug(base)
        subrace = _slug(sub_short) if sub_short else None
        return race or _slug(full), subrace

    def _extract_classes(self, data: Dict[str, Any]
                         ) -> Tuple[Dict[str, int], int, Dict[str, str]]:
        classes_map: Dict[str, int] = {}
        subclasses: Dict[str, str] = {}
        total = 0
        for c in data.get("classes") or []:
            definition = c.get("definition") or {}
            name = _slug(definition.get("name") or "")
            if not name:
                continue
            level = int(c.get("level", 1) or 1)
            classes_map[name] = level
            total += level
            subdef = c.get("subclassDefinition")
            if subdef and subdef.get("name"):
                subclasses[name] = _slug(subdef["name"])
        return classes_map, total, subclasses

    def _extract_ability_scores(self, data: Dict[str, Any],
                                modifiers: List[Dict[str, Any]]) -> Dict[str, int]:
        stats = {s["id"]: s.get("value") or 0 for s in data.get("stats") or []}
        bonus = {s["id"]: s.get("value") or 0 for s in data.get("bonusStats") or []}
        override = {s["id"]: s.get("value") for s in data.get("overrideStats") or []}

        scores: Dict[str, int] = {}
        for sid, ability in _STAT_IDS.items():
            if override.get(sid):
                scores[ability] = int(override[sid])
                continue
            base = int(stats.get(sid) or 0) + int(bonus.get(sid) or 0)
            for mod in modifiers:
                sub = mod.get("subType") or ""
                if sub != f"{_ABILITY_FULL[ability]}-score":
                    continue
                if mod.get("type") == "bonus":
                    base += int(mod.get("value") or 0)
                elif mod.get("type") == "set":
                    val = int(mod.get("value") or 0)
                    if val > base:
                        base = val
            scores[ability] = base
        return scores

    def _extract_hit_points(self, data: Dict[str, Any], con_score: int,
                            total_level: int) -> Tuple[int, int, int]:
        override = data.get("overrideHitPoints")
        base = int(data.get("baseHitPoints") or 0)
        bonus = int(data.get("bonusHitPoints") or 0)
        removed = int(data.get("removedHitPoints") or 0)
        temp = int(data.get("temporaryHitPoints") or 0)
        con_mod = (int(con_score) - 10) // 2
        if override:
            max_hp = int(override)
        else:
            max_hp = base + bonus + (con_mod * total_level)
        current = max(0, max_hp - removed)
        return max_hp, current, temp

    def _extract_pronoun(self, data: Dict[str, Any]) -> Optional[str]:
        for key in ("pronouns", "pronoun"):
            v = data.get(key)
            if v:
                return v
        return None

    def _iter_modifiers(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        modifiers = data.get("modifiers") or {}
        if isinstance(modifiers, dict):
            for bucket in ("race", "class", "background", "item", "feat",
                           "condition"):
                vals = modifiers.get(bucket) or []
                if isinstance(vals, list):
                    out.extend(vals)
        elif isinstance(modifiers, list):
            out.extend(modifiers)
        return out

    def _extract_modifiers_of_type(self, modifiers: List[Dict[str, Any]],
                                    mod_type: str,
                                    filter_set: Optional[Set[str]] = None,
                                    transform=None) -> List[str]:
        results: Set[str] = set()
        for mod in modifiers:
            if mod.get("type") != mod_type:
                continue
            sub = mod.get("subType") or mod.get("friendlySubtypeName")
            if not sub:
                continue
            slug = _slug(sub)
            if transform is not None:
                slug = transform(slug)
            if filter_set is not None and slug not in filter_set:
                continue
            results.add(slug)
        return sorted(results)

    def _extract_save_proficiencies(self, modifiers: List[Dict[str, Any]]) -> List[str]:
        out: Set[str] = set()
        for mod in modifiers:
            if mod.get("type") != "proficiency":
                continue
            sub = (mod.get("subType") or "").lower()
            for ability_short, ability_long in _ABILITY_FULL.items():
                if sub == f"{ability_long}-saving-throws":
                    out.add(ability_short)
        return sorted(out)

    def _extract_inventory(self, data: Dict[str, Any]
                            ) -> Tuple[List[str], List[Dict[str, Any]]]:
        known = _load_known_items()
        inventory: List[Dict[str, Any]] = []
        equipped: List[str] = []
        for item in data.get("inventory") or []:
            definition = item.get("definition") or {}
            name = definition.get("name") or ""
            slug = _normalize_item(_slug(name))
            if slug not in known:
                self._warn(f"unknown item dropped: {name!r} ({slug})")
                continue
            qty = int(item.get("quantity") or 1)
            inventory.append({"type": slug, "qty": qty})
            if item.get("equipped"):
                equipped.append(slug)
        return equipped, inventory

    def _extract_spells(self, data: Dict[str, Any],
                         classes_map: Dict[str, int]
                         ) -> Tuple[List[str], List[str], List[str]]:
        known = _load_known_spells()
        cantrips: List[str] = []
        prepared: List[str] = []
        spellbook: List[str] = []
        seen_cantrip: Set[str] = set()
        seen_prepared: Set[str] = set()
        seen_book: Set[str] = set()

        def _add(spell_obj: Dict[str, Any], force_prepared: bool,
                 owner_class: Optional[str]) -> None:
            definition = spell_obj.get("definition") or spell_obj
            name = definition.get("name") or ""
            slug = _slug(name)
            slug = _SPELL_ALIASES.get(slug, slug)
            if not slug:
                return
            if slug not in known:
                self._warn(f"unknown spell dropped: {name!r} ({slug})")
                return
            level = definition.get("level", 0) or 0
            is_prepared = bool(spell_obj.get("prepared")) or force_prepared
            always_prep = bool(spell_obj.get("alwaysPrepared"))
            if level == 0:
                if slug not in seen_cantrip:
                    seen_cantrip.add(slug)
                    cantrips.append(slug)
                return
            if owner_class == "wizard" and slug not in seen_book:
                seen_book.add(slug)
                spellbook.append(slug)
            if is_prepared or always_prep:
                if slug not in seen_prepared:
                    seen_prepared.add(slug)
                    prepared.append(slug)

        for entry in data.get("classSpells") or []:
            class_id = entry.get("characterClassId")
            owner_class: Optional[str] = None
            for c in data.get("classes") or []:
                if c.get("id") == class_id:
                    owner_class = _slug(
                        (c.get("definition") or {}).get("name") or "")
                    break
            for s in entry.get("spells") or []:
                _add(s, force_prepared=False, owner_class=owner_class)

        spells_section = data.get("spells") or {}
        if isinstance(spells_section, dict):
            for bucket in spells_section.values():
                if not isinstance(bucket, list):
                    continue
                for s in bucket:
                    _add(s, force_prepared=True, owner_class=None)

        return cantrips, prepared, spellbook

    def _compute_spell_slots(self, classes_map: Dict[str, int],
                              subclasses: Dict[str, str]
                              ) -> Dict[str, Dict[int, int]]:
        if not classes_map:
            return {}

        slots_out: Dict[str, Dict[int, int]] = {}

        warlock_level = classes_map.get("warlock", 0)
        if warlock_level:
            count, slot_lvl = _WARLOCK_PACT_SLOTS[min(warlock_level, 20)]
            slots_out["warlock"] = {slot_lvl: count}

        caster_level = 0
        for klass, lvl in classes_map.items():
            if klass in _FULL_CASTERS:
                caster_level += lvl
            elif klass in _HALF_CASTERS:
                caster_level += lvl // 2
            elif klass == "fighter" and subclasses.get("fighter") == "eldritch_knight":
                caster_level += lvl // 3
            elif klass == "rogue" and subclasses.get("rogue") == "arcane_trickster":
                caster_level += lvl // 3

        if caster_level <= 0:
            return slots_out

        table_row = _FULL_CASTER_SLOTS[min(caster_level, 20)]
        primary = (next((k for k in classes_map if k in _FULL_CASTERS), None)
                   or next((k for k in classes_map if k in _HALF_CASTERS), None))
        if primary:
            slots_out[primary] = {i + 1: n for i, n in enumerate(table_row)}
        return slots_out

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        warnings.warn(message)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import D&D Beyond characters to YAML format")
    parser.add_argument("character_id", nargs="?", type=int, default=None,
                        help="D&D Beyond character ID")
    parser.add_argument("--input", "-i",
                        help="Read a saved JSON payload instead of fetching")
    parser.add_argument("--output", "-o", help="Output file path (optional)")
    parser.add_argument("--cobalt-token",
                        help="Cobalt session token for private characters")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as a non-zero exit code")
    args = parser.parse_args(argv)

    if not args.character_id and not args.input:
        parser.error("provide a character_id or --input <file>")

    importer = BeyondImporter(strict=args.strict)
    try:
        text = importer.import_character(
            character_id=args.character_id,
            output_path=args.output,
            input_path=args.input,
            cobalt_token=args.cobalt_token,
        )
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"Error importing character: {exc}", file=sys.stderr)
        return 1

    if importer.warnings:
        for w in importer.warnings:
            print(f"warning: {w}", file=sys.stderr)

    if not args.output:
        print(text)
    return 2 if (args.strict and importer.warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
