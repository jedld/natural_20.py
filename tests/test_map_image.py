"""Tests for map image rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from natural20.map_image.grid import load_map_grid
from natural20.map_image.renderer import MapImageRenderer, RenderConfig, render_map_image
from natural20.yaml_loader import templates_root


@pytest.fixture
def tiny_map(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.yml"
    path.write_text(
        """
name: Tiny Test Map
description: A small room with walls and a chest.
map:
  size: [5, 4]
  base:
    - "#####"
    - "#...#"
    - "#.c.#"
    - "#####"
  base_1:
    - "....."
    - "....."
    - "....."
    - "....."
legend:
  c:
    name: chest
    type: chest
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def test_load_map_grid_dimensions(tiny_map: Path) -> None:
    grid = load_map_grid(tiny_map)
    assert grid.width == 5
    assert grid.height == 4
    assert grid.cell("base", 0, 0) == "#"
    assert grid.cell("base", 2, 2) == "c"


def test_render_procedural_png(tiny_map: Path, tmp_path: Path) -> None:
    output = tmp_path / "tiny.png"
    result = render_map_image(input_yaml=tiny_map, output=output, tile_size=32)
    assert result.is_file()
    image = Image.open(result)
    assert image.size == (5 * 32, 4 * 32)
    assert image.mode in {"RGBA", "RGB"}


def test_render_layers_and_jpeg(tiny_map: Path, tmp_path: Path) -> None:
    output = tmp_path / "tiny.jpg"
    render_map_image(
        input_yaml=tiny_map,
        output=output,
        tile_size=24,
        layers=["base"],
        image_format="jpeg",
    )
    image = Image.open(output)
    assert image.mode == "RGB"
    assert image.size == (5 * 24, 4 * 24)


def test_renderer_wall_and_floor_pixels(tiny_map: Path) -> None:
    grid = load_map_grid(tiny_map)
    renderer = MapImageRenderer(
        grid,
        RenderConfig(tile_size=16, layers=("base",), atmosphere=False, palette="stone"),
    )
    image = renderer.render()
    # Top-left wall should be darker than interior floor
    wall_pixel = image.getpixel((2, 2))
    floor_pixel = image.getpixel((18, 18))
    assert sum(wall_pixel[:3]) < sum(floor_pixel[:3])


def test_theme_inference() -> None:
    from natural20.map_image.tiles import theme_for_name

    assert theme_for_name("Thyros Sewers", "foul undercity") == "sewer"
    assert theme_for_name("Saint Elara Cathedral", "holy facade") == "cathedral"
    assert theme_for_name("City Streets", "gas-lit alleys", map_id="city_streets") == "street"


def test_object_icons_render() -> None:
    from natural20.map_image.tiles import object_icon

    for kind in ("teleporter", "chest", "altar", "candle", "note", "campfire", "pit_trap"):
        icon = object_icon(32, kind, "cathedral", 1)
        assert icon is not None
        assert icon.size == (32, 32)


def test_render_goblin_cave_from_templates(tmp_path: Path) -> None:
    map_path = templates_root() / "maps" / "goblin_cave.yml"
    if not map_path.is_file():
        pytest.skip("templates goblin_cave map missing")
    output = tmp_path / "goblin_cave.png"
    render_map_image(
        input_yaml=map_path,
        output=output,
        tile_size=48,
        palette="dirt",
    )
    image = Image.open(output)
    assert image.width == 10 * 48
    assert image.height == 10 * 48


@pytest.fixture
def batch_campaign(tmp_path: Path) -> Path:
    campaign = tmp_path / "campaign"
    (campaign / "maps").mkdir(parents=True)
    (campaign / "assets" / "maps").mkdir(parents=True)
    (campaign / "game.yml").write_text(
        """
name: Batch Test
starting_map: maps/has_bg
maps:
  has_bg: maps/has_bg
  missing_bg: maps/missing_bg
  no_bg: maps/no_bg
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
    (campaign / "index.json").write_text('{"tile_size": 32}\n', encoding="utf-8")

    def write_map(name: str, extra: str = "") -> None:
        (campaign / "maps" / f"{name}.yml").write_text(
            f"""
name: {name}
map:
  size: [4, 3]
  base:
    - "####"
    - "#..#"
    - "####"
{extra}
""".strip()
            + "\n",
            encoding="utf-8",
        )

    write_map("has_bg", "background_image: has_bg.png")
    (campaign / "assets" / "maps" / "has_bg.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    write_map("missing_bg", "background_image: missing_bg.png")
    write_map("no_bg")
    return campaign


def test_find_maps_needing_assets(batch_campaign: Path) -> None:
    from natural20.map_image.batch import find_maps_needing_assets

    jobs = find_maps_needing_assets(batch_campaign)
    by_id = {job.map_id: job for job in jobs}
    assert by_id["has_bg"].asset_exists is True
    assert by_id["missing_bg"].needs_render is True
    assert by_id["no_bg"].needs_render is True


def test_batch_render_missing_assets(batch_campaign: Path) -> None:
    from natural20.map_image.batch import batch_render_missing_map_assets

    results = batch_render_missing_map_assets(
        batch_campaign,
        update_yaml=True,
    )
    rendered = {result.map_id for result in results if not result.skipped}
    assert rendered == {"missing_bg", "no_bg"}
    assert (batch_campaign / "assets" / "maps" / "missing_bg.png").is_file()
    assert (batch_campaign / "assets" / "maps" / "no_bg.png").is_file()

    no_bg_yaml = (batch_campaign / "maps" / "no_bg.yml").read_text(encoding="utf-8")
    assert "background_image: no_bg.png" in no_bg_yaml


def test_batch_dry_run_lists_pending(batch_campaign: Path) -> None:
    from natural20.map_image.batch import find_maps_needing_assets

    jobs = [job for job in find_maps_needing_assets(batch_campaign) if job.needs_render]
    assert {job.map_id for job in jobs} == {"missing_bg", "no_bg"}

