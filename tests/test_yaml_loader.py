"""Tests for YAML template inheritance and campaign fallbacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from natural20.session import Session
from natural20.yaml_loader import (
  campaign_import_roots,
  deep_merge,
  load_campaign_resource_path,
  load_campaign_yaml,
  load_yaml,
  templates_root,
)


@pytest.fixture
def mini_campaign(tmp_path: Path) -> Path:
    campaign = tmp_path / "campaign"
    (campaign / "items").mkdir(parents=True)
    (campaign / "game.yml").write_text(
        """
name: Inherit Test
starting_map: maps/start
maps:
  start: maps/start
groups:
  a:
    default: true
    enemies: []
    neutral: []
    allies: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (campaign / "maps").mkdir()
    (campaign / "maps" / "start.yml").write_text(
        """
name: Start
map:
  base:
    - "."
legend: {}
npc: []
player_spawn_points:
  - [0, 0]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return campaign


def _write_game_yml(path: Path, *, imports: list[str] | None = None) -> None:
    imports_yaml = ""
    if imports:
        imports_yaml = "imports:\n" + "\n".join(f"  - {entry}" for entry in imports) + "\n"
    (path / "game.yml").write_text(
        (
            """
name: Inherit Test
starting_map: maps/start
maps:
  start: maps/start
groups:
  a:
    default: true
    enemies: []
    neutral: []
    allies: []
"""
            + imports_yaml
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (path / "maps").mkdir(exist_ok=True)
    (path / "maps" / "start.yml").write_text(
        """
name: Start
map:
  base:
    - "."
legend: {}
npc: []
player_spawn_points:
  - [0, 0]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_deep_merge_nested_dicts() -> None:
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    overlay = {"a": {"y": 9, "z": 3}, "c": 4}
    merged = deep_merge(base, overlay)
    assert merged == {"a": {"x": 1, "y": 9, "z": 3}, "b": 1, "c": 4}


def test_file_inherit_from_absolute_path(tmp_path: Path) -> None:
    parent = tmp_path / "parent.yml"
    child = tmp_path / "child.yml"
    parent.write_text(
        """
base_sword:
  name: Base Sword
  type: weapon
  weight: 3
""".strip()
        + "\n",
        encoding="utf-8",
    )
    child.write_text(
        f"""
inherit: {parent}

custom_badge:
  name: Custom Badge
  type: trinket
  weight: 0.1
""".strip()
        + "\n",
        encoding="utf-8",
    )

    data = load_yaml(child)
    assert data["base_sword"]["name"] == "Base Sword"
    assert data["custom_badge"]["name"] == "Custom Badge"
    assert "inherit" not in data


def test_file_inherit_templates_prefix() -> None:
    campaign = templates_root().parent / "user_levels" / "outcasts_path"
    if not (campaign / "items" / "equipment.yml").is_file():
        pytest.skip("outcasts_path campaign not present")
    data = load_campaign_yaml(campaign, "items", "equipment", merge_templates=False)
    assert "chain_mail" in data


def test_auto_merge_items_without_inherit(mini_campaign: Path) -> None:
    (mini_campaign / "items" / "equipment.yml").write_text(
        """
custom_badge:
  name: Custom Badge
  type: trinket
  weight: 0.1
""".strip()
        + "\n",
        encoding="utf-8",
    )

    data = load_campaign_yaml(mini_campaign, "items", "equipment")
    assert "chain_mail" in data
    assert data["custom_badge"]["name"] == "Custom Badge"


def test_entry_level_inherit(tmp_path: Path) -> None:
    path = tmp_path / "items.yml"
    path.write_text(
        """
holy_symbol:
  name: Holy Symbol
  type: trinket
  weight: 1

investigators_badge:
  inherit: holy_symbol
  name: Investigator's Badge
""".strip()
        + "\n",
        encoding="utf-8",
    )
    data = load_yaml(path)
    assert data["investigators_badge"]["type"] == "trinket"
    assert data["investigators_badge"]["name"] == "Investigator's Badge"
    assert "inherit" not in data["investigators_badge"]


def test_circular_inherit_raises(tmp_path: Path) -> None:
    a = tmp_path / "a.yml"
    b = tmp_path / "b.yml"
    a.write_text("inherit: b.yml\nkey: a\n", encoding="utf-8")
    b.write_text("inherit: a.yml\nkey: b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Circular"):
        load_yaml(a)


def test_session_loads_template_fallback_items(mini_campaign: Path) -> None:
    (mini_campaign / "items" / "equipment.yml").write_text(
        """
custom_badge:
  name: Custom Badge
  type: trinket
""".strip()
        + "\n",
        encoding="utf-8",
    )

    session = Session(root_path=str(mini_campaign))
    equipment = session.load_all_equipments()
    assert "chain_mail" in equipment
    assert "custom_badge" in equipment


def test_missing_campaign_item_file_falls_back_to_templates(mini_campaign: Path) -> None:
    data = load_campaign_yaml(mini_campaign, "items", "equipment")
    assert "chain_mail" in data


def test_campaign_import_roots_by_name(tmp_path: Path) -> None:
    campaigns = tmp_path / "campaigns"
    parent = campaigns / "base_campaign"
    child = campaigns / "child_campaign"
    parent.mkdir(parents=True)
    child.mkdir(parents=True)
    _write_game_yml(parent)
    _write_game_yml(child, imports=["base_campaign"])

    roots = campaign_import_roots(child)
    assert roots == [parent.resolve()]


def test_load_campaign_yaml_merges_imported_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates = tmp_path / "templates"
    (templates / "items").mkdir(parents=True)
    (templates / "items" / "equipment.yml").write_text(
        """
template_badge:
  name: Template Badge
  type: trinket
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NATURAL20_TEMPLATES_ROOT", str(templates))

    campaigns = tmp_path / "campaigns"
    parent = campaigns / "base_campaign"
    child = campaigns / "child_campaign"
    (parent / "items").mkdir(parents=True)
    (child / "items").mkdir(parents=True)
    _write_game_yml(parent)
    _write_game_yml(child, imports=["base_campaign"])

    (parent / "items" / "equipment.yml").write_text(
        """
shared_kit:
  name: Parent Shared Kit
  type: trinket
parent_only:
  name: Parent Only
  type: trinket
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (child / "items" / "equipment.yml").write_text(
        """
shared_kit:
  name: Child Override Kit
  type: trinket
child_only:
  name: Child Only
  type: trinket
""".strip()
        + "\n",
        encoding="utf-8",
    )

    data = load_campaign_yaml(child, "items", "equipment")
    assert data["template_badge"]["name"] == "Template Badge"
    assert data["parent_only"]["name"] == "Parent Only"
    assert data["shared_kit"]["name"] == "Child Override Kit"
    assert data["child_only"]["name"] == "Child Only"


def test_load_campaign_resource_path_falls_back_to_imported_campaign(tmp_path: Path) -> None:
    campaigns = tmp_path / "campaigns"
    parent = campaigns / "base_campaign"
    child = campaigns / "child_campaign"
    (parent / "races").mkdir(parents=True)
    child.mkdir(parents=True)
    _write_game_yml(parent)
    _write_game_yml(child, imports=["base_campaign"])

    (parent / "races" / "moon_touched.yml").write_text(
        """
name: Moon Touched
size: medium
""".strip()
        + "\n",
        encoding="utf-8",
    )

    race = load_campaign_resource_path(child, "races/moon_touched.yml")
    assert race["name"] == "Moon Touched"


def test_session_loads_imported_npc_info(tmp_path: Path) -> None:
    campaigns = tmp_path / "campaigns"
    parent = campaigns / "base_campaign"
    child = campaigns / "child_campaign"
    (parent / "npcs").mkdir(parents=True)
    child.mkdir(parents=True)
    _write_game_yml(parent)
    _write_game_yml(child, imports=["base_campaign"])

    (parent / "npcs" / "imported_wolf.yml").write_text(
        """
name: Imported Wolf
ability:
  str: 12
  dex: 15
  con: 12
  int: 3
  wis: 12
  cha: 6
actions:
  - name: bite
""".strip()
        + "\n",
        encoding="utf-8",
    )

    session = Session(root_path=str(child))
    info = session.npc_info()
    assert "imported_wolf" in info
    assert info["imported_wolf"]["name"] == "Imported Wolf"


def test_session_loads_imported_characters(tmp_path: Path) -> None:
    campaigns = tmp_path / "campaigns"
    parent = campaigns / "base_campaign"
    child = campaigns / "child_campaign"
    (parent / "characters").mkdir(parents=True)
    child.mkdir(parents=True)
    _write_game_yml(parent)
    _write_game_yml(child, imports=["base_campaign"])

    source_character = (
        Path(__file__).resolve().parent / "fixtures" / "high_elf_fighter.yml"
    )
    (parent / "characters" / "imported_hero.yml").write_text(
        source_character.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    session = Session(root_path=str(child))
    characters = session.load_characters()
    names = {character.name for character in characters}
    assert "Gomerin" in names
