"""Tests for item/spell icon scanning and generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from natural20.image_gen.campaign_assets import AssetJobResult
from natural20.image_gen.game_icons import (
    collect_action_icon_slugs,
    discover_effect_refs,
    discover_item_refs,
    discover_spell_refs,
    effect_icon_exists,
    generate_game_icons,
    item_icon_exists,
    prepare_square_icon,
    scan_missing_icons,
    spell_icon_exists,
    spell_needs_effect_icon,
)
from natural20.image_gen.spell_scroll_icons import (
    is_spell_scroll_item,
    render_spell_scroll_icon,
    spell_scroll_spell_slug,
)
from natural20.image_gen.mcp_client import GeneratedImage
from natural20.image_gen.prompts import action_icon_prompt, effect_icon_prompt, item_icon_negative, item_icon_prompt, item_visual_hint, spell_icon_prompt
from natural20.image_gen.web_optimize import optimize_icon_for_web
from natural20.utils.spell_loader import spell_is_implemented
from natural20.event_manager import EventManager
from natural20.session import Session


def _solid(size=64, color=(80, 120, 200, 255)) -> Image.Image:
    return Image.new("RGBA", (size, size), color)


def test_item_and_spell_icon_prompts_include_style():
    item = item_icon_prompt(
        name="longsword",
        label="Longsword",
        item_type="weapon",
        description="A long blade.",
        icon_style="flat style icons, bold outline",
        theme="The Goblin Ambush",
    )
    spell = spell_icon_prompt(
        name="firebolt",
        label="Fire Bolt",
        school="evocation",
        description="A streak of fire shoots toward a creature.",
        icon_style="flat style icons, bold outline",
        theme="The Goblin Ambush",
    )
    effect = effect_icon_prompt(
        name="detect_magic",
        label="Detect Magic",
        school="divination",
        icon_style="flat style icons, bold outline",
    )
    action = action_icon_prompt(
        slug="divine_smite",
        label="Divine Smite",
        icon_style="flat style icons, bold outline",
    )
    assert "flat style icons" in item
    assert "Longsword" in item or "longsword" in item
    assert "Goblin" not in item
    assert "flat vector art" in item
    assert "blade" in item.lower() or "sword" in item.lower()
    assert "flat style icons" in spell
    assert "flat style icons" in effect
    assert "flat style icons" in action
    assert "Fire Bolt" in spell
    assert "Detect Magic" in effect
    assert "streak of fire" not in spell
    assert "Goblin" not in spell
    assert "flat vector art" in spell
    assert "Status effect buff icon" in effect


def test_item_visual_hint_describes_sling_as_sling_not_gun():
    hint = item_visual_hint(name="sling", label="Sling", item_type="ranged_attack")
    assert "sling" in hint.lower()
    assert "gun" in hint.lower() or "not a gun" in hint.lower()


def test_item_visual_hint_for_armor():
    hint = item_visual_hint(name="ring_mail", label="Ring Mail", item_type="armor", subtype="heavy")
    assert "armor" in hint.lower()
    assert "ring" in hint.lower()
    assert "shield" in hint.lower()  # "not a shield"
    plate_hint = item_visual_hint(name="plate", label="Plate Armor", item_type="armor", subtype="heavy")
    assert "pauldron" in plate_hint.lower() or "torso" in plate_hint.lower()
    assert "shield" in plate_hint.lower()


def test_item_icon_negative_rejects_shields_for_armor():
    neg = item_icon_negative(name="plate", label="Plate Armor", item_type="armor")
    assert "shield" in neg
    assert "treasure chest" in neg
    sling_neg = item_icon_negative(name="sling", label="Sling")
    crossbow_neg = item_icon_negative(name="light_crossbow", label="Light Crossbow")
    assert "rifle" in sling_neg
    assert "rifle" in crossbow_neg
    assert "scope" in crossbow_neg


def test_prepare_square_icon_resizes_to_target():
    icon = prepare_square_icon(_solid(512), 128)
    assert icon.size == (128, 128)
    assert icon.mode == "RGB"


def test_scan_missing_icons_finds_gaps(tmp_path: Path):
    session = Session(root_path="templates", event_manager=EventManager())
    spell_dir = tmp_path / "spells"
    spell_dir.mkdir()
    # fireball is in templates spells but typically has no bundled icon
    missing = scan_missing_icons(
        session,
        items=False,
        spells=True,
        only=["fireball"],
        spell_output_dir=spell_dir,
    )
    assert any(ref.key == "fireball" for ref in missing)


def test_scan_missing_icons_force_includes_existing(tmp_path: Path):
    session = Session(root_path="templates", event_manager=EventManager())
    spell_dir = tmp_path / "spells"
    spell_dir.mkdir()
    existing = spell_dir / "spell_fireball.png"
    existing.write_bytes(b"png")
    missing = scan_missing_icons(
        session,
        items=False,
        spells=True,
        only=["fireball"],
        spell_output_dir=spell_dir,
        force=True,
    )
    assert any(ref.key == "fireball" for ref in missing)


def test_scan_missing_effect_icons(tmp_path: Path):
    session = Session(root_path="templates", event_manager=EventManager())
    effect_dir = tmp_path / "effects"
    effect_dir.mkdir()
    missing = scan_missing_icons(
        session,
        items=False,
        spells=False,
        actions=False,
        effects=True,
        effect_output_dir=effect_dir,
        only=["detect_magic"],
    )
    assert len(missing) == 1
    assert missing[0].kind == "effect"
    assert missing[0].output_path == effect_dir / "detect_magic.png"


def test_spell_needs_effect_icon_detects_concentration():
    assert spell_needs_effect_icon({"concentration": True, "type": "utility"})
    assert spell_needs_effect_icon({"type": "buff"})
    assert not spell_needs_effect_icon({"type": "damage"})


def test_spell_is_implemented_filters_generic_wizard_stubs():
    assert spell_is_implemented(
        "fireball",
        {"spell_class": "Natural20::Fireball"},
    )
    assert not spell_is_implemented(
        "knock",
        {"spell_class": "Natural20::Knock"},
    )
    assert spell_is_implemented("detect_magic", {"spell_class": "Natural20::DetectMagic"})


def test_discover_item_refs_default_excludes_objects_and_packs():
    session = Session(root_path="templates", event_manager=EventManager())
    refs = discover_item_refs(session)
    sources = {ref.source for ref in refs}
    keys = {ref.key for ref in refs}
    assert "objects" not in sources
    assert "equipment_packs" not in sources
    assert "chest" not in keys
    assert "dagger" in keys or "longsword" in keys


def test_discover_item_refs_can_include_objects_and_packs():
    session = Session(root_path="templates", event_manager=EventManager())
    refs = discover_item_refs(session, include_objects=True, include_packs=True)
    sources = {ref.source for ref in refs}
    assert "objects" in sources
    assert "equipment_packs" in sources


def test_discover_spell_refs_skips_unimplemented_stubs():
    session = Session(root_path="templates", event_manager=EventManager())
    refs = discover_spell_refs(session)
    keys = {ref.key for ref in refs}
    assert "fireball" in keys
    assert "knock" not in keys


def test_generate_game_icons_dry_run_and_mock(tmp_path: Path, monkeypatch):
    session = Session(root_path="templates", event_manager=EventManager())
    out_items = tmp_path / "items"
    out_spells = tmp_path / "spells"
    out_items.mkdir()
    out_spells.mkdir()

    refs = [
        discover_item_refs(session, item_output_dir=out_items)[0],
        discover_spell_refs(session, spell_output_dir=out_spells)[0],
    ]
    for ref in refs:
        ref.output_path = (
            out_items / f"{ref.image_name}.png"
            if ref.kind == "item"
            else out_spells / f"spell_{ref.key}.png"
        )

    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return GeneratedImage(image=_solid(256), summary="ok")

    report = generate_game_icons(
        session=session,
        missing=refs,
        generator=fake_generate,
        icon_style="flat style icons",
        force=True,
        item_size=64,
        spell_size=64,
        optimize=False,
    )
    assert not report.errors
    assert len(calls) == 2
    assert "flat style icons" in calls[0]["prompt"]
    assert refs[0].output_path.is_file()
    assert refs[1].output_path.is_file()


def test_item_icon_exists_respects_bundled_static():
    assert item_icon_exists("dagger")
    assert not item_icon_exists("definitely_not_a_real_item_xyz")


def test_collect_action_icon_slugs_includes_class_features():
    session = Session(root_path="templates", event_manager=EventManager())
    slugs = collect_action_icon_slugs(session)
    assert "divine_smite" in slugs
    assert "interact_open" in slugs
    assert "attack_melee" in slugs


def test_scan_missing_action_icons(tmp_path: Path):
    session = Session(root_path="templates", event_manager=EventManager())
    action_dir = tmp_path / "actions"
    action_dir.mkdir()
    missing = scan_missing_icons(
        session,
        items=False,
        spells=False,
        actions=True,
        effects=False,
        action_output_dir=action_dir,
        only=["divine_smite"],
    )
    assert len(missing) == 1
    assert missing[0].kind == "action"


def test_optimize_icon_for_web_reduces_or_preserves_size(tmp_path: Path):
    icon_path = tmp_path / "sample.png"
    Image.new("RGB", (256, 256), (40, 80, 120)).save(icon_path, format="PNG")
    before = icon_path.stat().st_size
    stats = optimize_icon_for_web(icon_path, max_dim=128, webp=True)
    assert stats["bytes_after"] <= before or icon_path.stat().st_size <= before
    assert (tmp_path / "sample.webp").is_file()


def test_spell_scroll_item_detection():
    assert is_spell_scroll_item({"type": "scroll", "spell": "magic_missile"})
    assert spell_scroll_spell_slug({"spell": "bless"}) == "bless"
    assert not is_spell_scroll_item({"type": "scroll"})
    assert not is_spell_scroll_item({"type": "potion", "spell": "healing"})


def test_render_spell_scroll_icon_composites_spell(tmp_path: Path):
    background = tmp_path / "scroll_bg.png"
    spell_icon = tmp_path / "spell.png"
    Image.new("RGB", (128, 128), (210, 180, 120)).save(background, format="PNG")
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(spell_icon, format="PNG")

    result = render_spell_scroll_icon(
        spell_slug="test_spell",
        spell_icon_path=spell_icon,
        background_path=background,
        scale_factor=1.0,
    )
    assert result.size == (128, 128)
    center = result.getpixel((64, 64))
    assert center[0] > 200


def test_generate_game_icons_uses_spell_scroll_compositor(tmp_path: Path):
    session = Session(root_path="templates", event_manager=EventManager())
    item_dir = tmp_path / "items"
    item_dir.mkdir()
    spell_dir = tmp_path / "spells"
    spell_dir.mkdir()
    background = tmp_path / "scroll_bg.png"
    spell_icon = spell_dir / "spell_magic_missile.png"
    Image.new("RGB", (128, 128), (210, 180, 120)).save(background, format="PNG")
    Image.new("RGBA", (32, 32), (0, 0, 255, 255)).save(spell_icon, format="PNG")

    refs = [
        ref
        for ref in discover_item_refs(session, item_output_dir=item_dir)
        if ref.key == "scroll_of_magic_missile"
    ]
    assert len(refs) == 1

    calls: list[dict] = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return GeneratedImage(image=_solid(256), summary="ok")

    from natural20.image_gen import spell_scroll_icons

    original_background = spell_scroll_icons.DEFAULT_SCROLL_BACKGROUND
    spell_scroll_icons.DEFAULT_SCROLL_BACKGROUND = background
    try:
        report = generate_game_icons(
            session=session,
            missing=refs,
            generator=fake_generate,
            force=True,
            item_size=64,
            optimize=False,
            spell_output_dir=spell_dir,
        )
    finally:
        spell_scroll_icons.DEFAULT_SCROLL_BACKGROUND = original_background

    assert not report.errors
    assert calls == []
    assert refs[0].output_path.is_file()
    assert report.results[0].reason == "spell-scroll-composite"
