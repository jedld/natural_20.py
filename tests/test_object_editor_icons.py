"""Tests for procedural object editor icon generation."""

from __future__ import annotations

from pathlib import Path

import yaml

from natural20.image_gen.object_editor_icons import (
    generate_object_editor_icons,
    render_object_editor_icon,
    resolve_editor_icon_kind,
    should_generate_editor_icon,
)


def test_resolve_editor_icon_kind_uses_token_image():
    assert resolve_editor_icon_kind("pit_trap", {"token_image": "spike_pit"}) == "spike_pit"
    assert resolve_editor_icon_kind("wooden_door", {"item_class": "DoorObject"}) == "wooden_door"


def test_should_skip_walls_and_door_walls():
    assert not should_generate_editor_icon("stone_wall", {"item_class": "StoneWall"})
    assert not should_generate_editor_icon("corner_door_tl", {"item_class": "DoorObjectWall"})
    assert should_generate_editor_icon("barrel", {"placeable": True})


def test_render_object_editor_icon_for_tree(tmp_path: Path):
    icon = render_object_editor_icon("tree", {"placeable": True}, size=64)
    assert icon is not None
    assert icon.size == (64, 64)
    out = tmp_path / "tree.png"
    icon.save(out)
    assert out.stat().st_size > 0


def test_generate_object_editor_icons_writes_missing(tmp_path: Path):
    objects = yaml.safe_load(Path("templates/items/objects.yml").read_text())
    results = generate_object_editor_icons(
        objects,
        output_dir=tmp_path,
        force=True,
    )
    written = [row for row in results if row[2] == "written"]
    assert any(row[0] == "barrel" for row in written)
    assert (tmp_path / "barrel.png").is_file()
