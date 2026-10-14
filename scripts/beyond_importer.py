#!/usr/bin/env python3
"""Import D&D Beyond characters into natural20.py YAML format.

This module exposes :class:`BeyondImporter`, which converts a JSON payload from
the public D&D Beyond character API (or a saved JSON file) into the YAML schema
consumed by :class:`natural20.player_character.PlayerCharacter`.

The importer focuses on producing data the engine actually reads — race /
subrace (including dragonborn ancestry), background, description/backstory,
stats, multiclass levels, skill / tool / language proficiencies, expertise,
weapon and armor proficiencies, resistances, prepared spells, cantrips,
spellbook contents (wizards), equipped gear and inventory.  Unknown items and
spells are filtered (with warnings) so the resulting YAML can be loaded
without surprising lookup failures.

Common D&D Beyond naming quirks (magic ``+N`` suffixes, ``Leather`` vs
``leather_armor``, Criminal/Spy backgrounds, domain subclasses) are normalized
to the engine's canonical IDs.
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
_ABILITY_BY_ID: Dict[int, str] = {
    1: "strength", 2: "dexterity", 3: "constitution",
    4: "intelligence", 5: "wisdom", 6: "charisma",
}

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
    "variant human": ("human", None),
    "standard human": ("human", None),
    "black dragonborn": ("dragonborn", "black"),
    "blue dragonborn": ("dragonborn", "blue"),
    "brass dragonborn": ("dragonborn", "brass"),
    "bronze dragonborn": ("dragonborn", "bronze"),
    "copper dragonborn": ("dragonborn", "copper"),
    "gold dragonborn": ("dragonborn", "gold"),
    "green dragonborn": ("dragonborn", "green"),
    "red dragonborn": ("dragonborn", "red"),
    "silver dragonborn": ("dragonborn", "silver"),
    "white dragonborn": ("dragonborn", "white"),
}

# D&D Beyond background display names -> templates/backgrounds/*.yml keys.
_BACKGROUND_ALIASES: Dict[str, str] = {
    "criminal_spy": "criminal",
    "criminal": "criminal",
    "folk_hero": "folk_hero",
    "guild_artisan_guild_merchant": "guild_artisan",
    "guild_artisan": "guild_artisan",
    "noble_knight": "noble",
    "sailor_pirate": "sailor",
    "soldier": "soldier",
    "acolyte": "acolyte",
    "charlatan": "charlatan",
    "entertainer": "entertainer",
    "hermit": "hermit",
    "outlander": "outlander",
    "sage": "sage",
}

# Classes that treat all known leveled spells as available without preparation.
_ALWAYS_PREPARED_CASTERS = frozenset({"sorcerer", "ranger", "bard", "warlock"})

# D&D Beyond source ids for the 2024 core books (PHB, DMG, MM).
_SOURCES_2024 = {145, 146, 147}
# Feats whose engine behavior depends on the edition (see feat_editions).
_EDITION_SENSITIVE_FEATS = {"great_weapon_master"}
# 2024 class features a 2014 class YAML doesn't grant.
_EDITION_CLASS_FEATURES: Dict[str, Tuple[str, ...]] = {
    "paladin": ("abjure_foes", "radiant_strikes", "weapon_mastery"),
}
_CONDITION_NAMES = {
    "blinded", "charmed", "deafened", "exhaustion", "frightened", "grappled",
    "incapacitated", "invisible", "paralyzed", "petrified", "poisoned",
    "prone", "restrained", "stunned", "unconscious",
}


def _is_2024_source(definition: Dict[str, Any]) -> bool:
    return any((src or {}).get("sourceId") in _SOURCES_2024
               for src in definition.get("sources") or [])


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
    "leather": "leather_armor",
    "studded_leather_armor": "studded_leather",
    "studded_leather": "studded_leather",
    "chain_mail_armor": "chain_mail",
    "chain_shirt_armor": "chain_shirt",
    "plate_armor": "plate",
    "half_plate_armor": "half_plate",
    "rations_1_day": "rations",
    "ration_1_day": "rations",
    "rope_hempen_50_feet": "rope",
    "hempen_rope_50_feet": "rope",
    "piton": "pitons",
    "quiver_of_20_arrows": "arrows",
    "quiver": "arrows",
    "arcane_focus_crystal": "crystal",
    "arcane_focus_orb": "orb",
    "arcane_focus_rod": "rod",
    "arcane_focus_staff": "staff",
    "arcane_focus_wand": "wand",
    "holy_symbol_emblem": "holy_symbol",
    "holy_symbol_reliquary": "holy_symbol",
    "holy_symbol_symbol": "holy_symbol",
    "potion_of_healing_greater": "potion_of_healing_greater",
    "ink_1_ounce_bottle": "ink",
    "parchment_one_sheet": "parchment",
    "small_knife": "small_knife",
    "climbers_kit": "climbers_kit",
    "oil": "oil_flask",
    "flask_of_oil": "oil_flask",
    "travelers_clothes": "clothes_traveler",
    "common_clothes": "clothes_common",
    "ball_bearings_bag_of_1_000": "ball_bearings",
    "crossbow_light": "light_crossbow",
    "crossbow_heavy": "heavy_crossbow",
    "crossbow_hand": "hand_crossbow",
    "robe": "robes",
    "flask_or_tankard": "flask",
    "tankard": "flask",
    "electrum": "electrum_piece",
    "splint_armor": "splint",
    "scale_mail_armor": "scale_mail",
    "breastplate_armor": "breastplate",
}

# DDB "Mithral <armor>" names map to ``mithral_<base armor id>``.
_MITHRAL_PREFIX = "mithral_"

# DDB prefixes some item names with a bracketed count, e.g. "[5] Elixir of Flight".
_BRACKET_COUNT_RE = re.compile(r"^\s*\[\s*\d+\s*\]\s*")

# Subclass slugs that differ between DDB naming and engine YAML keys.
_SUBCLASS_ALIASES: Dict[str, str] = {
    "life_domain": "life",
    "knowledge_domain": "knowledge",
    "light_domain": "light",
    "nature_domain": "nature",
    "tempest_domain": "tempest",
    "trickery_domain": "trickery",
    "war_domain": "war",
    "grave_domain": "grave",
    "forge_domain": "forge",
    "order_domain": "order",
    "peace_domain": "peace",
    "twilight_domain": "twilight",
}

# Spell name aliases (DDB -> engine canonical).  Both keys/values are slugged.
_SPELL_ALIASES: Dict[str, str] = {
    "fire_bolt": "firebolt",
}

_ITEM_CACHE: Optional[Set[str]] = None
_SPELL_CACHE: Optional[Set[str]] = None
_CAMPAIGN_ITEM_CACHE: Dict[str, Set[str]] = {}
_CAMPAIGN_SPELL_CACHE: Dict[str, Set[str]] = {}

_ITEM_RESOURCES = ("weapons", "equipment", "objects", "magic_items")

_PLUS_WORDS: Dict[int, str] = {1: "one", 2: "two", 3: "three"}

_CURRENCY_ITEMS: Dict[str, str] = {
    "cp": "copper_piece",
    "sp": "silver_piece",
    "ep": "electrum_piece",
    "gp": "gold_piece",
    "pp": "platinum_piece",
}

# DDB armorTypeId values for body armor (4 is shield).
_BODY_ARMOR_TYPE_IDS = frozenset({1, 2, 3})

# DDB inventory entries that are class-feature placeholders, not real gear.
_PSEUDO_ITEM_PREFIXES = ("class feature:",)

_MASTERY_NAMES = frozenset({
    "cleave", "graze", "nick", "push", "sap", "slow", "topple", "vex",
})
_MASTERY_OPTION_RE = re.compile(r"^\s*(?P<weapon>.+?)\s*\((?P<mastery>[A-Za-z]+)\)\s*$")

_DDB_CHARACTER_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?dndbeyond\.com/characters/(?P<id>\d+)",
    re.IGNORECASE,
)


def parse_character_id_from_url(url: str) -> Optional[int]:
    """Extract a D&D Beyond numeric character id from a sheet URL."""
    if not url:
        return None
    text = str(url).strip()
    match = _DDB_CHARACTER_URL_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group("id"))
    except (TypeError, ValueError):
        return None


def _slug(value: Any) -> str:
    """Convert an arbitrary display string into a snake_case identifier."""
    if value is None:
        return ""
    s = re.sub(r"['\u2019]", "", str(value).lower())
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def _load_campaign_keys(campaign_root: str, resources: Tuple[str, ...]) -> Set[str]:
    """Item/spell ids visible to a campaign (local, imports, expansions, templates)."""
    from natural20.yaml_loader import load_campaign_yaml

    keys: Set[str] = set()
    for resource in resources:
        try:
            data = load_campaign_yaml(campaign_root, "items", resource) or {}
        except Exception:
            continue
        if isinstance(data, dict):
            keys.update(k for k in data.keys() if k != "inherit")
    return keys


def _load_known_items(campaign_root: Optional[str] = None) -> Set[str]:
    global _ITEM_CACHE
    if campaign_root:
        key = str(Path(campaign_root).resolve())
        if key not in _CAMPAIGN_ITEM_CACHE:
            _CAMPAIGN_ITEM_CACHE[key] = _load_campaign_keys(key, _ITEM_RESOURCES)
        return _CAMPAIGN_ITEM_CACHE[key]
    if _ITEM_CACHE is not None:
        return _ITEM_CACHE
    items: Set[str] = set()
    base = _templates_dir() / "items"
    for name in (f"{r}.yml" for r in _ITEM_RESOURCES):
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


_ITEM_DEFINITION_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_item_definitions(campaign_root: Optional[str] = None) -> Dict[str, Any]:
    """Item YAML entries by id (campaign view when ``campaign_root`` is set)."""
    cache_key = str(Path(campaign_root).resolve()) if campaign_root else ""
    if cache_key in _ITEM_DEFINITION_CACHE:
        return _ITEM_DEFINITION_CACHE[cache_key]
    merged: Dict[str, Any] = {}
    for resource in _ITEM_RESOURCES:
        data: Any = {}
        try:
            if campaign_root:
                from natural20.yaml_loader import load_campaign_yaml
                data = load_campaign_yaml(cache_key, "items", resource) or {}
            else:
                from natural20.yaml_loader import load_yaml
                data = load_yaml(_templates_dir() / "items" / f"{resource}.yml") or {}
        except Exception:
            data = {}
        if isinstance(data, dict):
            for key, value in data.items():
                if key != "inherit":
                    merged.setdefault(key, value)
    _ITEM_DEFINITION_CACHE[cache_key] = merged
    return merged


def _load_known_spells(campaign_root: Optional[str] = None) -> Set[str]:
    global _SPELL_CACHE
    if campaign_root:
        key = str(Path(campaign_root).resolve())
        if key not in _CAMPAIGN_SPELL_CACHE:
            _CAMPAIGN_SPELL_CACHE[key] = _load_campaign_keys(key, ("spells",))
        return _CAMPAIGN_SPELL_CACHE[key]
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


def _strip_magic_bonus_suffix(name: str) -> str:
    """Remove trailing +N enchantment markers from DDB item display names."""
    return re.sub(r",?\s*\+\d+\s*$", "", str(name), flags=re.IGNORECASE).strip()


def _strip_bracket_count(name: str) -> str:
    """Drop a leading DDB bracketed count such as ``[5] `` from an item name."""
    return _BRACKET_COUNT_RE.sub("", str(name or "")).strip()


def _item_slug_from_name(name: str) -> str:
    cleaned = _strip_magic_bonus_suffix(_strip_bracket_count(name))
    slug = _slug(cleaned)
    slug = _ITEM_ALIASES.get(slug, slug)
    if slug.startswith(_MITHRAL_PREFIX):
        base = slug[len(_MITHRAL_PREFIX):]
        slug = _MITHRAL_PREFIX + _ITEM_ALIASES.get(base, base)
    return slug


def _normalize_item(slug: str) -> str:
    return _ITEM_ALIASES.get(slug, slug)


def _resolve_item_slug(name: str, known: Set[str]) -> Optional[str]:
    """Map a DDB item display name to a known engine item id, or ``None``.

    Tries, in order: ``<base>_plus_<n>`` for ``+N`` items, the plain slug, a
    ``<base>_<variant>`` id for ``Base (Variant)`` names, and finally the base
    item without its variant (e.g. ``Dragon Scale Mail (Bronze)``).
    ``Mithral <armor>`` / ``Mithral Armor (<armor>)`` map to ``mithral_<armor>``.
    """
    text = _strip_bracket_count(name)
    bonus_match = re.search(r"\+(\d+)\s*$", text)
    base_slug = _item_slug_from_name(text)
    candidates: List[str] = []
    if bonus_match:
        word = _PLUS_WORDS.get(int(bonus_match.group(1)))
        if word:
            candidates.append(f"{base_slug}_plus_{word}")
    candidates.append(base_slug)
    variant = re.match(r"^(?P<base>.+?)\s*\((?P<variant>[^)]+)\)\s*$",
                       _strip_magic_bonus_suffix(text))
    if variant:
        root = _item_slug_from_name(variant.group("base"))
        if root == f"{_MITHRAL_PREFIX}armor":
            candidates.append(_item_slug_from_name(f"Mithral {variant.group('variant')}"))
        candidates.append(f"{root}_{_slug(variant.group('variant'))}")
        candidates.append(root)
    for candidate in candidates:
        if candidate in known:
            return candidate
    return None


def _normalize_background(slug: str) -> str:
    return _BACKGROUND_ALIASES.get(slug, slug)


def _normalize_subclass(klass: str, subclass_name: str) -> str:
    slug = _slug(subclass_name)
    slug = _SUBCLASS_ALIASES.get(slug, slug)
    if klass == "cleric" and slug.endswith("_domain"):
        slug = slug[: -len("_domain")]
    return slug


class BeyondImporter:
    """Convert D&D Beyond character payloads to natural20.py YAML."""

    DEFAULT_API = "https://character-service.dndbeyond.com/character/v5/character"

    def __init__(self, *, base_url: Optional[str] = None,
                 user_agent: str = "natural20.py-importer/1.0",
                 strict: bool = False,
                 campaign_root: Optional[str] = None):
        self.base_url = base_url or self.DEFAULT_API
        self.user_agent = user_agent
        self.strict = strict
        self.campaign_root = campaign_root
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
        sheet_ability = self._extract_ability_scores(character_data, modifiers)
        ability = self._extract_ability_scores(
            character_data, modifiers,
            skip_item_ids=self._engine_ability_item_ids(character_data))
        max_hp, current_hp, temp_hp = self._extract_hit_points(
            character_data, sheet_ability.get("con", 10), total_level)

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
        resistances = self._extract_modifiers_of_type(
            [m for m in modifiers if m.get("_bucket") == "item"], "resistance")
        feats = sorted({_slug((f.get("definition") or {}).get("name") or "")
                        for f in character_data.get("feats", []) or []
                        if f.get("definition")})
        feats = [f for f in feats if f]
        maneuvers = self._extract_maneuvers(character_data)

        equipped_items, inventory = self._extract_inventory(character_data)
        cantrips, prepared, spellbook = self._extract_spells(
            character_data, classes_map)
        spell_slots = self._compute_spell_slots(classes_map, subclass_fields)
        flavor = self._extract_character_flavor(character_data)

        name = character_data.get("name") or "Unnamed"
        token_letter = (str(name).strip()[:1] or "P").upper()

        yaml_data: Dict[str, Any] = {
            "name": name,
            "race": race,
        }
        if subrace:
            yaml_data["subrace"] = subrace
            if race == "dragonborn":
                yaml_data["ancestry"] = subrace
        display_name = (character_data.get("socialName") or "").strip()
        if display_name and display_name != name:
            yaml_data["display_name"] = display_name
        gender = character_data.get("gender")
        if gender:
            yaml_data["gender"] = gender
        pronoun = self._extract_pronoun(character_data)
        if pronoun:
            yaml_data["pronoun"] = pronoun
        if flavor.get("description"):
            yaml_data["description"] = flavor["description"]
        if flavor.get("backstory"):
            yaml_data["backstory"] = flavor["backstory"]
        for key in (
            "outward_appearance",
            "personality_traits",
            "ideals",
            "bonds",
            "flaws",
            "faith",
            "age",
            "hair",
            "eyes",
            "skin",
            "height",
            "weight",
        ):
            if flavor.get(key):
                yaml_data[key] = flavor[key]

        yaml_data["classes"] = classes_map
        yaml_data["level"] = total_level
        yaml_data["xp"] = int(character_data.get("currentXp") or character_data.get("xp") or 0)
        yaml_data["hit_die"] = "inherit"
        yaml_data["max_hp"] = max_hp
        yaml_data["hp"] = current_hp
        if temp_hp:
            yaml_data["temporary_hp"] = temp_hp
        yaml_data["ability"] = ability

        for klass, sub in subclass_fields.items():
            field = _SUBCLASS_KEY_BY_CLASS.get(klass) or self._class_yaml(klass).get("subclass_property")
            if field and sub:
                yaml_data[field] = sub
        race_edition = getattr(self, "_race_edition_value", None)
        if race_edition:
            yaml_data["race_edition"] = race_edition

        if save_profs:
            yaml_data["saving_throw_proficiencies"] = save_profs
        if skills:
            yaml_data["skills"] = sorted(skills)
        if expertise:
            yaml_data["expertise"] = sorted(expertise)
        if tools:
            yaml_data["tools"] = sorted(tools)
            yaml_data["tool_proficiencies"] = sorted(tools)
        if weapon_profs:
            yaml_data["weapon_proficiencies"] = sorted(weapon_profs)
        languages = [l for l in languages if not _slug(l).startswith("choose_")]
        if languages:
            yaml_data["languages"] = sorted({_slug(l) for l in languages})
        item_resistances = self._equipped_item_resistances(equipped_items)
        resistances = [r for r in resistances if _slug(r) not in item_resistances] + [
            m.get("subType") for m in modifiers
            if m.get("type") == "resistance" and m.get("_bucket") != "item" and m.get("subType")
        ]
        if resistances:
            yaml_data["resistances"] = sorted({_slug(r) for r in resistances})
        condition_immunities = self._extract_condition_immunities(modifiers, equipped_items)
        if condition_immunities:
            yaml_data["condition_immunities"] = condition_immunities
        if feats:
            yaml_data["feats"] = feats
        yaml_data.update(self._extract_feature_choices(character_data))
        yaml_data.update(self._edition_overrides(character_data, classes_map))
        if maneuvers:
            yaml_data["maneuvers"] = maneuvers
        masteries = self._extract_weapon_masteries(character_data)
        if masteries:
            yaml_data["known_weapon_masteries"] = masteries
        if "martial_adept" in feats:
            yaml_data["superiority_die"] = "1d6"
            yaml_data["superiority_dice"] = 1

        spell_abilities = self._extract_spell_abilities(character_data)
        if spell_abilities:
            yaml_data["spell_abilities"] = spell_abilities
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
            yaml_data["background"] = _normalize_background(
                _slug(background["name"]))

        yaml_data["equipped"] = equipped_items
        if getattr(self, "_tracks_attunement", False):
            yaml_data["attuned"] = list(self.attuned_items)
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
    def _campaign_ruleset(self) -> str:
        if not self.campaign_root:
            return "5e-2014"
        try:
            game = yaml.safe_load((Path(self.campaign_root) / "game.yml").read_text()) or {}
        except Exception:
            return "5e-2014"
        return str(game.get("ruleset") or "5e-2014")

    def _equipped_item_resistances(self, equipped: List[str]) -> Set[str]:
        """Damage resistances already granted by equipped item YAML (``resistances``)."""
        found: Set[str] = set()
        if not equipped:
            return found
        try:
            from natural20.yaml_loader import load_campaign_yaml
        except Exception:
            return found
        root = self.campaign_root or str(_templates_dir().parent)
        catalogs = []
        for resource in ("magic_items", "equipment", "weapons"):
            try:
                catalogs.append(load_campaign_yaml(root, "items", resource) or {})
            except Exception:
                continue
        for slug in equipped:
            for catalog in catalogs:
                entry = catalog.get(slug)
                if isinstance(entry, dict):
                    found.update(_slug(r) for r in entry.get("resistances") or [])
                    break
        return found

    def _extract_condition_immunities(self, modifiers: List[Dict[str, Any]],
                                      equipped: Optional[List[str]] = None) -> List[str]:
        """Unconditional condition immunities (aura/situational ones are engine
        features). Item immunities the equipped item YAML already grants
        (``condition_immunities``) are left to the engine."""
        item_granted: Set[str] = set()
        if equipped:
            defs = _load_item_definitions(self.campaign_root)
            for slug in equipped:
                entry = defs.get(slug)
                if isinstance(entry, dict):
                    item_granted.update(_slug(c) for c in entry.get("condition_immunities") or [])
        out: Set[str] = set()
        for m in modifiers:
            if m.get("type") != "immunity" or m.get("restriction"):
                continue
            sub = _slug(m.get("subType") or "")
            if sub not in _CONDITION_NAMES:
                continue
            if m.get("_bucket") == "item" and sub in item_granted:
                continue
            out.add(sub)
        return sorted(out)

    def _extract_feature_choices(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Class-feature options picked on DDB (Eldritch Invocations) and the
        spells they or Mystic Arcanum grant.

        Options of a class feature whose slug is listed in the class YAML
        ``feature_choices`` become that sheet list (``eldritch_invocations``).
        ``Agonizing Blast (Eldritch Blast)`` also records the cantrip in
        ``invocation_spells``. Spells granted by a picked option land in
        ``class_spells`` so they count as that class's spells (Pact of the
        Tome), and ``Mystic Arcanum (Level N Spell)`` spells in
        ``mystic_arcanum: {N: slug}``.
        """
        out: Dict[str, Any] = {}
        options = (data.get("options") or {}).get("class") or []
        known_spells = _load_known_spells(self.campaign_root)
        option_class: Dict[Any, str] = {}
        arcanum_features: Dict[Any, Tuple[str, int]] = {}
        for c in data.get("classes") or []:
            klass = _slug((c.get("definition") or {}).get("name") or "")
            choice_keys = set(self._class_yaml(klass).get("feature_choices") or [])
            for cf in c.get("classFeatures") or []:
                fdef = cf.get("definition") or {}
                fname = re.sub(r"^\d+:\s*", "", fdef.get("name") or "")
                arcanum = re.match(r"^(?P<base>.+?)\s*\(Level (?P<level>\d+) Spell\)\s*$", fname)
                if arcanum:
                    arcanum_features[fdef.get("id")] = (_slug(arcanum.group("base")), int(arcanum.group("level")))
                    continue
                key = _slug(fname)
                if key not in choice_keys:
                    continue
                picks = out.setdefault(key, [])
                for option in options:
                    if option.get("componentId") != fdef.get("id"):
                        continue
                    label = (option.get("definition") or {}).get("name") or ""
                    match = re.match(r"^(?P<name>.+?)\s*\((?P<spell>[^)]+)\)\s*$", label)
                    pick = _slug(match.group("name") if match else label)
                    if not pick or pick in picks:
                        continue
                    picks.append(pick)
                    option_class[(option.get("definition") or {}).get("id")] = klass
                    if match:
                        spell = _SPELL_ALIASES.get(_slug(match.group("spell")), _slug(match.group("spell")))
                        if spell in known_spells:
                            out.setdefault("invocation_spells", {})[pick] = spell
        for spell_obj in (data.get("spells") or {}).get("class") or []:
            definition = spell_obj.get("definition") or {}
            slug = _SPELL_ALIASES.get(_slug(definition.get("name")), _slug(definition.get("name")))
            if slug not in known_spells:
                continue
            component = spell_obj.get("componentId")
            if component in arcanum_features:
                prop, level = arcanum_features[component]
                out.setdefault(prop, {})[level] = slug
            elif component in option_class:
                spells = out.setdefault("class_spells", {}).setdefault(option_class[component], [])
                if slug not in spells:
                    spells.append(slug)
        return {k: v for k, v in out.items() if v}

    def _edition_overrides(self, data: Dict[str, Any], classes_map: Dict[str, int]) -> Dict[str, Any]:
        """2024-sourced feats/classes imported into a campaign on another ruleset.

        Records ``feat_editions`` for 2024 feats with edition-specific engine
        behavior, adds the 2024 class features the campaign's class YAML won't
        grant as ``class_features``, and the 2024 paladin Channel Divinity
        count as ``channel_divinity_uses``.
        """
        if self._campaign_ruleset() == "5e-2024":
            return {}
        out: Dict[str, Any] = {}
        editions = {}
        for f in data.get("feats") or []:
            definition = f.get("definition") or {}
            if _is_2024_source(definition) and definition.get("name"):
                editions[_slug(definition["name"])] = "5e-2024"
        editions = {k: v for k, v in editions.items() if k in _EDITION_SENSITIVE_FEATS}
        if editions:
            out["feat_editions"] = dict(sorted(editions.items()))
        features: List[str] = []
        for c in data.get("classes") or []:
            definition = c.get("definition") or {}
            if not _is_2024_source(definition):
                continue
            klass = _slug(definition.get("name") or "")
            level = int(c.get("level", 1) or 1)
            for cf in c.get("classFeatures") or []:
                fdef = cf.get("definition") or {}
                if int(fdef.get("requiredLevel") or 99) > level:
                    continue
                slug = _slug(re.sub(r"^\d+:\s*", "", fdef.get("name") or ""))
                if slug in _EDITION_CLASS_FEATURES.get(klass, ()) and slug not in features:
                    features.append(slug)
            if klass == "paladin" and level >= 3:
                out["channel_divinity_uses"] = 3 if level >= 11 else 2
        if features:
            out["class_features"] = features
        return out

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
        race = race or _slug(full)
        self._race_edition_value = self._race_edition(race_obj, race)
        if not subrace:
            subrace = self._ancestry_from_race_options(data, race)
        return race, subrace

    def _race_edition(self, race_obj: Dict[str, Any], race: str) -> Optional[str]:
        """``5e-2024`` for a 2024 race imported into a campaign on other rules,
        when the engine ships that race's 2024 overlay."""
        if not _is_2024_source(race_obj) or self._campaign_ruleset() == "5e-2024":
            return None
        try:
            from natural20.yaml_loader import ruleset_overlay_root
            root = ruleset_overlay_root("5e-2024")
        except Exception:
            return None
        if root is None or not (root / "races" / f"{race}.yml").is_file():
            return None
        return "5e-2024"

    def _known_subraces(self, race: str) -> Set[str]:
        try:
            edition = getattr(self, "_race_edition_value", None)
            doc = None
            if edition:
                from natural20.yaml_loader import ruleset_overlay_root
                path = ruleset_overlay_root(edition) / "races" / f"{race}.yml"
                doc = yaml.safe_load(path.read_text()) or {}
            else:
                from natural20.yaml_loader import load_campaign_resource_path
                root = self.campaign_root or str(_templates_dir().parent)
                doc = load_campaign_resource_path(root, f"races/{race}.yml") or {}
        except Exception:
            return set()
        if not isinstance(doc, dict):
            return set()
        return set((doc.get("subrace") or doc.get("subraces") or {}).keys())

    def _ancestry_from_race_options(self, data: Dict[str, Any], race: str) -> Optional[str]:
        """2024 lineage choices (e.g. Goliath "Hill's Tumble (Hill Giant)") live in race options."""
        known = self._known_subraces(race)
        if not known:
            return None
        options = (data.get("options") or {}).get("race") or []
        for opt in options:
            name = ((opt or {}).get("definition") or {}).get("name") or ""
            match = re.search(r"\(([^()]+)\)\s*$", name)
            if match and _slug(match.group(1)) in known:
                return _slug(match.group(1))
            if _slug(name) in known:
                return _slug(name)
        return None

    def _class_yaml(self, klass: str) -> Dict[str, Any]:
        """Campaign class YAML (templates, imports and expansion packs)."""
        try:
            from natural20.yaml_loader import load_campaign_resource_path
            root = self.campaign_root or str(_templates_dir().parent)
            doc = load_campaign_resource_path(root, f"char_classes/{klass}.yml") or {}
        except Exception:
            return {}
        return doc if isinstance(doc, dict) else {}

    def _extract_spell_abilities(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Casting ability of race/feat/background spells (``spell_abilities``)."""
        known = _load_known_spells(self.campaign_root)
        out: Dict[str, str] = {}
        spells_section = data.get("spells") or {}
        if not isinstance(spells_section, dict):
            return out
        for bucket, entries in spells_section.items():
            if bucket == "class" or not isinstance(entries, list):
                continue
            for entry in entries:
                ability = _ABILITY_BY_ID.get((entry or {}).get("spellCastingAbilityId"))
                name = ((entry or {}).get("definition") or {}).get("name") or ""
                slug = _SPELL_ALIASES.get(_slug(name), _slug(name))
                if ability and slug in known and slug not in out:
                    out[slug] = ability
        return out

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
                subclasses[name] = _normalize_subclass(name, subdef["name"])
        return classes_map, total, subclasses

    def _trait_text(self, value: Any) -> str:
        if not value:
            return ""
        if isinstance(value, list):
            lines: List[str] = []
            for item in value:
                if isinstance(item, dict):
                    line = (item.get("description") or "").strip()
                else:
                    line = str(item).strip()
                if line:
                    lines.append(line)
            return "\n".join(lines)
        return str(value).strip()

    def _extract_character_flavor(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Pull description/backstory and structured personality fields from D&D Beyond."""
        flavor: Dict[str, str] = {}
        notes = data.get("notes") or {}
        if isinstance(notes, dict):
            backstory = (notes.get("backstory") or "").strip()
            if backstory:
                flavor["backstory"] = backstory

        traits = data.get("traits") or {}
        if isinstance(traits, dict):
            pieces: List[str] = []
            appearance = (traits.get("appearance") or "").strip()
            if appearance:
                flavor["outward_appearance"] = appearance
                pieces.append(f"Appearance: {appearance}")
            trait_map = (
                ("personalityTraits", "personality_traits", "Personality"),
                ("ideals", "ideals", "Ideals"),
                ("bonds", "bonds", "Bonds"),
                ("flaws", "flaws", "Flaws"),
            )
            for ddb_key, yaml_key, label in trait_map:
                text = self._trait_text(traits.get(ddb_key))
                if text:
                    flavor[yaml_key] = text
                    pieces.append(f"{label}: {text}")
            if pieces:
                flavor["description"] = "\n\n".join(pieces)

        for field in ("faith", "age", "hair", "eyes", "skin", "height", "weight"):
            value = data.get(field)
            if value not in (None, ""):
                flavor[field] = str(value).strip()
        return flavor

    def _engine_ability_item_ids(self, data: Dict[str, Any]) -> Set[Any]:
        """DDB item definition ids whose ability changes the engine applies itself.

        Their ``modifiers.item`` score bonuses are left out of the imported
        base scores so the equipped item (``ability_bonus`` / ``ability_set``)
        is not counted twice.
        """
        definitions = _load_item_definitions(self.campaign_root)
        known = set(definitions)
        ids: Set[Any] = set()
        for item in data.get("inventory") or []:
            definition = item.get("definition") or {}
            slug = _resolve_item_slug(definition.get("name") or "", known)
            entry = definitions.get(slug) if slug else None
            if isinstance(entry, dict) and (entry.get("ability_bonus") or entry.get("ability_set")):
                if definition.get("id") is not None:
                    ids.add(definition.get("id"))
        return ids

    def _extract_ability_scores(self, data: Dict[str, Any],
                                modifiers: List[Dict[str, Any]],
                                skip_item_ids: Optional[Set[Any]] = None) -> Dict[str, int]:
        if skip_item_ids:
            modifiers = [m for m in modifiers
                         if not (m.get("_bucket") == "item" and m.get("componentId") in skip_item_ids)]
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

    def _extract_maneuvers(self, data: Dict[str, Any]) -> List[str]:
        maneuvers: Set[str] = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                name = value.get("name")
                if isinstance(name, str) and name.lower().startswith("maneuvers:"):
                    maneuver_name = name.split(":", 1)[1].strip()
                    if maneuver_name:
                        maneuvers.add(_slug(maneuver_name))
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(data.get("actions") or {})
        return sorted(maneuvers)

    def _iter_modifiers(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        modifiers = data.get("modifiers") or {}
        if isinstance(modifiers, dict):
            for bucket in ("race", "class", "background", "item", "feat",
                           "condition"):
                vals = modifiers.get(bucket) or []
                if isinstance(vals, list):
                    out.extend(dict(v, _bucket=bucket) for v in vals if isinstance(v, dict))
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
        known = _load_known_items(self.campaign_root)
        quantities: Dict[str, int] = {}
        equipped: List[str] = []
        self.attuned_items: List[str] = []
        self._tracks_attunement = False
        body_armor: List[Tuple[Tuple[int, int, int], str]] = []
        for item in data.get("inventory") or []:
            definition = item.get("definition") or {}
            name = definition.get("name") or ""
            if name.strip().lower().startswith(_PSEUDO_ITEM_PREFIXES):
                continue
            slug = _resolve_item_slug(name, known)
            if slug is None:
                self._warn(f"unknown item dropped: {name!r} ({_item_slug_from_name(name)})")
                continue
            raw_qty = item.get("quantity")
            qty = 1 if raw_qty is None else int(raw_qty)
            if qty <= 0:
                continue
            quantities[slug] = quantities.get(slug, 0) + qty
            if definition.get("canAttune") or item.get("isAttuned"):
                self._tracks_attunement = True
            if item.get("isAttuned") and slug not in self.attuned_items:
                self.attuned_items.append(slug)
            if not item.get("equipped") or slug in equipped:
                continue
            if definition.get("armorTypeId") in _BODY_ARMOR_TYPE_IDS:
                rank = (
                    1 if item.get("isAttuned") else 0,
                    1 if definition.get("magic") else 0,
                    int(definition.get("armorClass") or 0),
                )
                body_armor.append((rank, slug))
                continue
            equipped.append(slug)
        if body_armor:
            body_armor.sort(key=lambda entry: entry[0], reverse=True)
            equipped.insert(0, body_armor[0][1])
            for _, extra in body_armor[1:]:
                self._warn(f"multiple body armors equipped; left {extra!r} unequipped")
        for coin, amount in (data.get("currencies") or {}).items():
            amount = int(amount or 0)
            if amount <= 0:
                continue
            slug = _CURRENCY_ITEMS.get(coin)
            if slug and slug in known:
                quantities[slug] = quantities.get(slug, 0) + amount
            else:
                self._warn(f"currency not imported: {amount} {coin}")
        inventory = [{"type": slug, "qty": qty} for slug, qty in quantities.items()]
        return equipped, inventory

    def _extract_weapon_masteries(self, data: Dict[str, Any]) -> List[str]:
        """Mastery properties picked on DDB as ``Weapon (Mastery)`` options."""
        found: Set[str] = set()
        options = data.get("options") or {}
        if not isinstance(options, dict):
            return []
        for bucket in options.values():
            for option in bucket or []:
                if not isinstance(option, dict):
                    continue
                label = (option.get("definition") or {}).get("name") or ""
                match = _MASTERY_OPTION_RE.match(label)
                if match and match.group("mastery").lower() in _MASTERY_NAMES:
                    found.add(match.group("mastery").lower())
        return sorted(found)

    def _extract_spells(self, data: Dict[str, Any],
                         classes_map: Dict[str, int]
                         ) -> Tuple[List[str], List[str], List[str]]:
        known = _load_known_spells(self.campaign_root)
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
            treat_as_prepared = (
                owner_class in _ALWAYS_PREPARED_CASTERS
                or is_prepared
                or always_prep
            )
            if level == 0:
                if slug not in seen_cantrip:
                    seen_cantrip.add(slug)
                    cantrips.append(slug)
                return
            if owner_class == "wizard" and slug not in seen_book:
                seen_book.add(slug)
                spellbook.append(slug)
            if treat_as_prepared:
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
                # Single-class half casters (and 2024 multiclassing) round up;
                # 2014 half casters get no slots at level 1.
                if len(classes_map) == 1 or self._campaign_ruleset() == "5e-2024":
                    if lvl >= 2 or self._campaign_ruleset() == "5e-2024":
                        caster_level += (lvl + 1) // 2
                else:
                    caster_level += lvl // 2
            elif klass == "fighter" and subclasses.get("fighter") == "eldritch_knight":
                caster_level += lvl // 3
            elif klass == "rogue" and subclasses.get("rogue") == "arcane_trickster":
                caster_level += lvl // 3
            else:
                spellcasting = self._class_yaml(klass).get("spellcasting") or {}
                if spellcasting.get("progression"):
                    from natural20.entity_class.data_driven import caster_level_for
                    caster_level += caster_level_for(spellcasting["progression"], lvl)

        if caster_level <= 0:
            return slots_out

        table_row = _FULL_CASTER_SLOTS[min(caster_level, 20)]
        primary = (next((k for k in classes_map if k in _FULL_CASTERS), None)
                   or next((k for k in classes_map if k in _HALF_CASTERS), None)
                   or next((k for k in classes_map
                            if (self._class_yaml(k).get("spellcasting") or {}).get("progression")), None))
        if primary:
            slots_out[primary] = {i + 1: n for i, n in enumerate(table_row)}
        return slots_out

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        warnings.warn(message)


def _resize_ddb_avatar_url(
    url: str,
    *,
    width: int,
    height: int,
    fit: str,
) -> str:
    """Rewrite D&D Beyond avatar CDN query params for desired dimensions."""
    base = str(url or "").strip().split("?", 1)[0]
    if not base:
        return ""
    return f"{base}?width={width}&height={height}&fit={fit}&quality=95&auto=webp"


def extract_avatar_urls(character_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(portrait_url, token_url)`` from a D&D Beyond character payload.

    Priority for the player's chosen art:
    1. ``decorations.avatarUrl`` — the character's selected avatar/portrait.
    2. ``race.portraitAvatarUrl`` / ``race.largeAvatarUrl`` — stock race art (fallback).

    The token URL reuses the character avatar when available; otherwise it falls
    back to the race portrait cropped for a map token.
    """
    decorations = character_data.get("decorations") or {}
    race = character_data.get("race") or {}

    char_avatar = str(decorations.get("avatarUrl") or "").strip() or None
    race_portrait = (
        str(race.get("portraitAvatarUrl") or "").strip()
        or str(race.get("largeAvatarUrl") or "").strip()
        or str(race.get("avatarUrl") or "").strip()
        or None
    )

    portrait_source = char_avatar or race_portrait
    if not portrait_source:
        return None, None

    portrait_url = _resize_ddb_avatar_url(
        portrait_source, width=1000, height=1000, fit="bounds"
    )
    token_source = char_avatar or portrait_source
    token_url = _resize_ddb_avatar_url(
        token_source, width=256, height=256, fit="crop"
    )
    return portrait_url, token_url


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
    parser.add_argument("--campaign",
                        help="Campaign folder whose items/spells (plus imports "
                             "and templates) are valid import targets")
    args = parser.parse_args(argv)

    if not args.character_id and not args.input:
        parser.error("provide a character_id or --input <file>")

    if args.campaign:
        repo_root = str(Path(__file__).resolve().parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
    importer = BeyondImporter(strict=args.strict, campaign_root=args.campaign)
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
