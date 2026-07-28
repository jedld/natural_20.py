"""Tests for MCP map texture packs."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from natural20.image_gen.mcp_client import GeneratedImage
from natural20.map_image.gen_textures import ensure_theme_textures, sample_texture
from natural20.map_image.tiles import floor_tile, theme_for_name


def test_theme_inference_tavern_docks():
    assert theme_for_name("The Drowning Rat", "a tavern", "tavern") == "tavern"
    assert theme_for_name("River Docks", "wet pier", "docks") == "docks"
    assert theme_for_name("Sewers", "muck", "sewers") == "sewer"


def test_ensure_theme_textures_mock(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("N20_MAP_TEXTURE_ROOT", str(tmp_path))

    def fake_generate(**kwargs):
        color = (
            (20, 180, 90, 255)
            if "slime" in kwargs["prompt"].lower() or "sewer" in kwargs["prompt"].lower()
            else (180, 40, 40, 255)
        )
        return GeneratedImage(image=Image.new("RGBA", (64, 64), color))

    written = ensure_theme_textures(["sewer"], root=tmp_path, force=True, generator=fake_generate)
    assert len(written) == 3
    assert (tmp_path / "sewer" / "floor.png").is_file()

    from natural20.map_image import gen_textures

    gen_textures.clear_texture_cache()
    # Point loader at tmp_path
    monkeypatch.setenv("N20_MAP_TEXTURE_ROOT", str(tmp_path))
    gen_textures.clear_texture_cache()
    tile = floor_tile(32, "sewer", 1)
    assert tile.size == (32, 32)
    px = tile.getpixel((16, 16))
    assert px[1] > px[0]


def test_sample_texture_resize():
    atlas = Image.new("RGBA", (128, 128), (10, 20, 30, 255))
    tile = sample_texture(atlas, 40, seed=99)
    assert tile.size == (40, 40)
