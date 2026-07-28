"""Tests for campaign validator and repair tooling."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from natural20.campaign_repair import RepairOptions, repair_campaign
from natural20.campaign_validator import ValidateOptions, validate_campaign
from natural20.campaign_validator.catalog import CampaignCatalog


@pytest.fixture
def broken_campaign(tmp_path: Path) -> Path:
    campaign = tmp_path / "broken_campaign"
    (campaign / "maps").mkdir(parents=True)
    (campaign / "characters").mkdir()
    (campaign / "items").mkdir()

    (campaign / "game.yml").write_text(
        """
name: Broken Campaign
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
    (campaign / "index.json").write_text(
        """
{
  "tile_size": 70,
  "title": "Broken",
  "login_background": "assets/login.png",
  "map": "maps/start",
  "soundtracks": [],
  "logins": [],
  "default_controllers": []
}
""".strip(),
        encoding="utf-8",
    )
    (campaign / "maps" / "start.yml").write_text(
        """
name: Start
map:
  base:
    - "..."
legend:
  G:
    type: goblin_chest
    name: Goblin Chest
npc: []
player_spawn_points:
  - [0, 0]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (campaign / "items" / "objects.yml").write_text("chest:\n  name: Chest\n  type: chest\n", encoding="utf-8")
    (campaign / "items" / "spells.yml").write_text("firebolt:\n  label: Fire Bolt\n  level: 0\n", encoding="utf-8")
    (campaign / "characters" / "wizard.yml").write_text(
        """
name: Test Wizard
race: elf
classes:
  wizard: 1
prepared_spells:
  - firebolt
  - missing_spell
inventory:
  - type: unknown_potion
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return campaign


def test_catalog_merges_templates_and_campaign(broken_campaign: Path) -> None:
    catalog = CampaignCatalog(broken_campaign)
    assert catalog.spell_exists("firebolt")
    assert catalog.object_exists("chest")
    assert not catalog.spell_exists("missing_spell")


def test_validator_reports_missing_references(broken_campaign: Path) -> None:
    report = validate_campaign(
        broken_campaign,
        ValidateOptions(static_only=True, skip_formatting=True),
    )
    messages = " ".join(issue.message for issue in report.issues)
    assert "unknown spell 'missing_spell'" in messages
    assert "unknown item 'unknown_potion'" in messages
    assert "unknown object type 'goblin_chest'" in messages


def test_validator_reports_yaml_formatting(tmp_path: Path) -> None:
    campaign = tmp_path / "fmt"
    campaign.mkdir()
    (campaign / "game.yml").write_text("name: test\t\n", encoding="utf-8")
    report = validate_campaign(campaign, ValidateOptions(static_only=True, skip_references=True))
    assert any(issue.code == "yaml_format_tabs" for issue in report.issues)


def test_repair_stub_without_llm(broken_campaign: Path) -> None:
    report = validate_campaign(
        broken_campaign,
        ValidateOptions(static_only=True, skip_formatting=True),
    )
    proposals = repair_campaign(
        broken_campaign,
        report,
        RepairOptions(use_llm=False, apply=True, dry_run=False),
    )
    assert proposals
    spells = yaml.safe_load((broken_campaign / "items" / "spells.yml").read_text(encoding="utf-8"))
    assert "missing_spell" in spells
