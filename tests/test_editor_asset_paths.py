"""Tests for editor icon path routing."""

from __future__ import annotations

from natural20.image_gen.editor_asset_paths import (
    editor_output_dir_for_object,
    migrate_bundled_editor_icon,
    object_editor_scope,
)


def test_object_editor_scope_template_vs_campaign(tmp_path, monkeypatch):
    import natural20.image_gen.editor_asset_paths as paths

    templates = tmp_path / "templates"
    (templates / "items").mkdir(parents=True)
    (templates / "items" / "objects.yml").write_text("barrel:\n  placeable: true\n", encoding="utf-8")
    monkeypatch.setattr(paths, "templates_root", lambda: templates)
    monkeypatch.setattr(paths, "templates_editor_dir", lambda: templates / "assets" / "editor")

    campaign = tmp_path / "user_levels" / "demo"
    (campaign / "items").mkdir(parents=True)
    (campaign / "items" / "objects.yml").write_text("custom_prop:\n  placeable: true\n", encoding="utf-8")
    monkeypatch.setattr(paths, "_REPO_ROOT", tmp_path)

    assert object_editor_scope("barrel") == "template"
    assert object_editor_scope("custom_prop", campaign_root=campaign) == "campaign"
    assert editor_output_dir_for_object("barrel") == templates / "assets" / "editor"
    assert editor_output_dir_for_object("custom_prop", campaign_root=campaign) == campaign / "assets" / "editor"


def test_migrate_bundled_editor_icon_moves_template_object(tmp_path, monkeypatch):
    import natural20.image_gen.editor_asset_paths as paths

    templates = tmp_path / "templates"
    (templates / "items").mkdir(parents=True)
    (templates / "items" / "objects.yml").write_text("tree:\n  placeable: true\n", encoding="utf-8")
    monkeypatch.setattr(paths, "templates_root", lambda: templates)

    bundled = tmp_path / "webapp" / "static" / "assets" / "editor"
    bundled.mkdir(parents=True)
    source = bundled / "tree.png"
    source.write_bytes(b"png")
    monkeypatch.setattr(paths, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(paths, "bundled_editor_dir", lambda: bundled)
    monkeypatch.setattr(paths, "templates_editor_dir", lambda: templates / "assets" / "editor")

    moves = migrate_bundled_editor_icon("tree.png", move=True)
    assert moves
    target = templates / "assets" / "editor" / "tree.png"
    assert target.is_file()
    assert not source.is_file()
