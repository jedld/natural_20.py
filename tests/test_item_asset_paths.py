"""Tests for campaign vs template item icon ownership."""

from __future__ import annotations

from pathlib import Path

from natural20.event_manager import EventManager
from natural20.image_gen.game_icons import discover_item_refs, item_icon_exists
from natural20.image_gen.item_asset_paths import (
    campaign_item_dir,
    item_definition_owner,
    item_icon_output_dir,
    item_icon_scope,
    resolve_item_icon_file,
)
from natural20.session import Session


def _write_catalog(root: Path, *, equipment: str = "", weapons: str = "") -> None:
    root.mkdir(parents=True, exist_ok=True)
    items = root / "items"
    items.mkdir(parents=True, exist_ok=True)
    (items / "equipment.yml").write_text(equipment, encoding="utf-8")
    if weapons:
        (items / "weapons.yml").write_text(weapons, encoding="utf-8")


def test_item_icon_scope_template_vs_campaign(tmp_path, monkeypatch):
    import natural20.image_gen.item_asset_paths as paths

    templates = tmp_path / "templates"
    _write_catalog(templates, equipment="torch:\n  type: gear\n")
    monkeypatch.setattr(paths, "templates_root", lambda: templates)

    campaign = tmp_path / "user_levels" / "demo"
    campaign.mkdir(parents=True)
    (campaign / "game.yml").write_text("name: Demo\n", encoding="utf-8")
    _write_catalog(campaign, equipment="skin_pouch:\n  type: container\n")

    assert item_icon_scope("torch") == "template"
    assert item_icon_scope("skin_pouch", campaign_root=campaign) == "campaign"
    assert item_definition_owner("skin_pouch", campaign_root=campaign) == (
        "campaign",
        campaign.resolve(),
    )
    assert item_icon_output_dir("torch", campaign_root=campaign) == paths.bundled_item_dir()
    assert item_icon_output_dir("skin_pouch", campaign_root=campaign) == campaign_item_dir(
        campaign
    )


def test_campaign_only_item_never_writes_to_bundled(tmp_path, monkeypatch):
    import natural20.image_gen.item_asset_paths as paths

    templates = tmp_path / "templates"
    _write_catalog(templates, equipment="torch:\n  type: gear\n")
    monkeypatch.setattr(paths, "templates_root", lambda: templates)

    campaign = tmp_path / "demo"
    campaign.mkdir()
    (campaign / "game.yml").write_text("name: Demo\n", encoding="utf-8")
    _write_catalog(campaign, equipment="crystal_orb:\n  type: gear\n")

    bundled = item_icon_output_dir(
        "crystal_orb",
        campaign_root=campaign,
        write_to="bundled",
    )
    assert bundled == campaign_item_dir(campaign)


def test_resolve_item_icon_file_prefers_campaign_over_bundled(tmp_path, monkeypatch):
    import natural20.image_gen.item_asset_paths as paths

    templates = tmp_path / "templates"
    templates.mkdir()
    monkeypatch.setattr(paths, "templates_root", lambda: templates)

    bundled = tmp_path / "static" / "assets" / "items"
    bundled.mkdir(parents=True)
    (bundled / "skin_pouch.png").write_bytes(b"bundled")
    monkeypatch.setattr(paths, "bundled_item_dir", lambda: bundled)

    campaign = tmp_path / "demo"
    (campaign / "assets" / "items").mkdir(parents=True)
    (campaign / "assets" / "items" / "skin_pouch.png").write_bytes(b"campaign")

    found = resolve_item_icon_file("skin_pouch.png", campaign_root=campaign)
    assert found is not None
    assert found.read_bytes() == b"campaign"


def test_item_icon_exists_ignores_stray_bundled_file_for_campaign_item(
    tmp_path, monkeypatch
):
    import natural20.image_gen.item_asset_paths as paths

    templates = tmp_path / "templates"
    _write_catalog(templates, equipment="torch:\n  type: gear\n")
    monkeypatch.setattr(paths, "templates_root", lambda: templates)

    bundled = tmp_path / "static" / "assets" / "items"
    bundled.mkdir(parents=True)
    (bundled / "skin_pouch.png").write_bytes(b"stray")
    monkeypatch.setattr(paths, "bundled_item_dir", lambda: bundled)

    campaign = tmp_path / "demo"
    campaign.mkdir()
    (campaign / "game.yml").write_text("name: Demo\n", encoding="utf-8")
    _write_catalog(campaign, equipment="skin_pouch:\n  type: container\n")

    assert not item_icon_exists(
        "skin_pouch",
        campaign_root=campaign,
        item_id="skin_pouch",
    )


def test_discover_item_refs_routes_campaign_only_items(tmp_path, monkeypatch):
    import natural20.image_gen.item_asset_paths as paths
    import natural20.yaml_loader as yaml_loader

    templates = tmp_path / "templates"
    _write_catalog(
        templates,
        equipment="dagger:\n  name: Dagger\n  type: melee_attack\n",
        weapons="dagger:\n  name: Dagger\n  type: melee_attack\n",
    )
    monkeypatch.setattr(paths, "templates_root", lambda: templates)
    monkeypatch.setattr(yaml_loader, "templates_root", lambda: templates)

    campaign = tmp_path / "demo"
    campaign.mkdir()
    (campaign / "game.yml").write_text("name: Demo\nmaps: {}\n", encoding="utf-8")
    _write_catalog(
        campaign,
        equipment="skin_pouch:\n  name: Pouch\n  type: container\n",
    )

    session = Session(root_path=str(campaign), event_manager=EventManager())
    refs = {
        ref.key: ref
        for ref in discover_item_refs(session, campaign_root=campaign, write_to="auto")
    }
    pouch = refs["skin_pouch"]
    assert pouch.scope == "campaign"
    assert pouch.output_path == campaign / "assets" / "items" / "skin_pouch.png"

    dagger = refs["dagger"]
    assert dagger.scope == "template"
    assert dagger.output_path == paths.bundled_item_dir() / "dagger.png"


def test_webapp_item_route_prefers_campaign_file(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from webapp.blueprints.helpers.asset_utils import resolve_asset_category_file
    import webapp.blueprints.helpers.asset_utils as asset_utils

    bundled = tmp_path / "static" / "assets" / "items"
    bundled.mkdir(parents=True)
    (bundled / "skin_pouch.png").write_bytes(b"bundled")
    monkeypatch.setattr(
        asset_utils,
        "bundled_asset_path",
        lambda category, filename: (
            bundled / filename
            if category == "items" and (bundled / filename).is_file()
            else None
        ),
    )

    campaign = tmp_path / "demo"
    (campaign / "assets" / "items").mkdir(parents=True)
    (campaign / "assets" / "items" / "skin_pouch.png").write_bytes(b"campaign")
    session = SimpleNamespace(root_path=str(campaign))

    file_path, fallback = resolve_asset_category_file(session, "items", "skin_pouch.png")
    assert fallback is None
    assert file_path is not None
    assert file_path.read_bytes() == b"campaign"
