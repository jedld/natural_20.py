"""Tests for YAML template inheritance and campaign fallbacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from natural20.session import Session
from natural20.yaml_loader import deep_merge, load_campaign_yaml, load_yaml, templates_root


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
