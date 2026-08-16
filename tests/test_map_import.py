"""Tests for battlemap tile-wise import."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from natural20.map_import import ImportKnobs, import_battlemap, knobs_json_schema
from natural20.map_import.compare import compare_map_properties
from natural20.map_import.consistency import apply_consistency_rules
from natural20.map_import.dimensions import parse_dimensions_from_name
from natural20.map_import.export import grid_to_map_properties
from natural20.map_import.ink import EdgeBits, detect_ink_edges
from natural20.map_import.json_util import parse_json_object
from natural20.map_import.model import ClassificationGrid, TileRecord
from natural20.map_import.taxonomy import mapping_for, normalize_class
from natural20.map_image.grid import map_grid_from_properties

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "scripts" / "import_battlemap.py"


def _paint_room(path: Path, width: int = 8, height: int = 6, tile: int = 16) -> Path:
    img = Image.new("RGB", (width * tile, height * tile), (200, 190, 170))
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            color = (200, 190, 170)
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                color = (12, 10, 9)
            if x == 3 and y == height - 1:
                color = (140, 80, 30)  # door in south wall
            if x == 3 and y == 3:
                color = (220, 180, 40)  # chest-ish
            for py in range(y * tile, (y + 1) * tile):
                for px in range(x * tile, (x + 1) * tile):
                    pixels[px, py] = color
    img.save(path)
    return path


def test_parse_dimensions_from_filename() -> None:
    assert parse_dimensions_from_name("tavern_22x17.png") == (22, 17)
    assert parse_dimensions_from_name("Map-40x30-grid.webp") == (40, 30)
    assert parse_dimensions_from_name("no_size.png") is None


def test_taxonomy_mappings() -> None:
    assert mapping_for("wall").base_token == "#"
    assert mapping_for("door", "wooden_door", orientation="vertical").base_token == "|"
    chest = mapping_for("object", "chest")
    assert chest.object_type == "chest"
    assert mapping_for("object", "table").object_type == "barrel"
    assert normalize_class("stone wall") == "wall"


def test_consistency_isolated_wall() -> None:
    grid = ClassificationGrid(5, 5)
    for y in range(5):
        for x in range(5):
            cls = "wall" if x in {0, 4} or y in {0, 4} else "floor"
            grid.set(TileRecord(x=x, y=y, tile_class=cls, confidence=0.9, source="test"))
    grid.set(TileRecord(x=2, y=2, tile_class="wall", confidence=0.4, source="test"))
    fixes = apply_consistency_rules(grid)
    assert any(f["x"] == 2 and f["y"] == 2 for f in fixes)
    assert grid.tiles[2][2].tile_class != "wall"


def test_heuristic_import_writes_playable_yaml(tmp_path: Path) -> None:
    image = _paint_room(tmp_path / "room_8x6.png")
    knobs = ImportKnobs(
        image=str(image),
        provider="heuristic",
        name="Test Room",
        map_id="test_room",
        calibrate_grid=False,
    )
    result = import_battlemap(knobs, workdir=tmp_path / "work", output=tmp_path / "room.yml")
    assert result.spec.width == 8
    assert result.spec.height == 6
    assert (tmp_path / "work" / "tiles" / "0_0.png").is_file()
    assert (tmp_path / "work" / "ascii.txt").is_file()
    assert (tmp_path / "work" / "classifications.json").is_file()
    props = result.properties
    grid = map_grid_from_properties(props)
    assert grid.width == 8
    assert grid.height == 6
    walls = sum(1 for x in range(8) for y in range(6) if grid.cell("base", x, y) == "#")
    assert walls >= 8  # outer frame mostly walls
    floors = sum(1 for x in range(8) for y in range(6) if grid.cell("base", x, y) == ".")
    assert floors >= 4
    yaml_text = (tmp_path / "room.yml").read_text(encoding="utf-8")
    assert "name: Test Room" in yaml_text
    assert "background_image: room_8x6.png" in yaml_text


def test_mock_provider_and_adventure_overlay(tmp_path: Path) -> None:
    image = _paint_room(tmp_path / "hall_8x6.png")
    knobs = ImportKnobs(
        image=str(image),
        width=8,
        height=6,
        provider="mock",
        name="Hall",
        adventure_text="A dusty hall with a closed south door. Adventurers enter from the center.",
        calibrate_grid=False,
    )
    result = import_battlemap(knobs, workdir=tmp_path / "work")
    assert "classify" in result.phases_run
    assert result.adventure_report.get("applied") or result.adventure_report.get("annotations", 0) >= 0
    anns = result.properties.get("map_annotations") or []
    assert any(a.get("id") == "main_room" for a in anns)


def test_print_schema_and_cli(tmp_path: Path) -> None:
    schema = knobs_json_schema()
    assert schema["properties"]["image"]
    assert "ollama" in schema["properties"]["provider"]["enum"]
    printed = subprocess.check_output([sys.executable, str(CLI), "--print-schema"], cwd=REPO, text=True)
    assert '"Natural20BattlemapImportKnobs"' in printed or "Natural20BattlemapImportKnobs" in printed
    image = _paint_room(tmp_path / "cell_8x6.png")
    completed = subprocess.run(
        [
            sys.executable,
            str(CLI),
            str(image),
            "--provider",
            "heuristic",
            "--name",
            "Cell",
            "--no-calibrate-grid",
            "--workdir",
            str(tmp_path / "wd"),
            "-o",
            str(tmp_path / "cell.yml"),
            "--json",
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert (tmp_path / "cell.yml").is_file()
    report = json.loads((tmp_path / "wd" / "report.json").read_text(encoding="utf-8"))
    assert report["grid"]["width"] == 8


def test_export_preserves_doors_and_legend() -> None:
    grid = ClassificationGrid(4, 4)
    for y in range(4):
        for x in range(4):
            cls = "wall" if x in {0, 3} or y in {0, 3} else "floor"
            grid.set(TileRecord(x=x, y=y, tile_class=cls, source="test", confidence=1.0))
    grid.set(TileRecord(x=1, y=3, tile_class="door", subtype="wooden_door", orientation="horizontal", source="test", confidence=1.0))
    grid.set(TileRecord(x=2, y=2, tile_class="object", subtype="chest", source="test", confidence=1.0))
    props = grid_to_map_properties(grid, name="Doors")
    assert any("-" in row for row in props["map"]["base"])
    assert "c" in props["legend"]
    assert props["legend"]["c"]["type"] == "chest"


def _paint_thin_room(path: Path, width: int = 6, height: int = 6, tile: int = 48) -> Path:
    """Floorplan-style room: thin black ink on cell edges, beige floor fill."""
    img = Image.new("RGB", (width * tile, height * tile), (230, 220, 200))
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 1, 1, width - 2, height - 2

    def edge(cx: int, cy: int, side: str, *, gap: bool = False) -> None:
        left, top = cx * tile, cy * tile
        right, bottom = left + tile - 1, top + tile - 1
        w = 3
        color = (12, 10, 9)
        if side == "N":
            pts = [(left, top), (right, top)]
        elif side == "S":
            pts = [(left, bottom), (right, bottom)]
        elif side == "W":
            pts = [(left, top), (left, bottom)]
        else:
            pts = [(right, top), (right, bottom)]
        if not gap:
            draw.line(pts, fill=color, width=w)
            return
        ax, ay = pts[0]
        bx, by = pts[1]
        draw.line([(ax, ay), (ax + (bx - ax) // 3, ay + (by - ay) // 3)], fill=color, width=w)
        draw.line([(ax + 2 * (bx - ax) // 3, ay + 2 * (by - ay) // 3), (bx, by)], fill=color, width=w)

    for x in range(x0, x1 + 1):
        edge(x, y0, "N")
        gap = x == (x0 + x1) // 2
        edge(x, y1, "S", gap=gap)
    for y in range(y0, y1 + 1):
        edge(x0, y, "W")
        edge(x1, y, "E")
    img.save(path)
    return path


def test_occupancy_to_thin_walls_room_outline() -> None:
    from natural20.map_import.thin_wall import occupancy_to_thin_walls, thin_wall_legend

    occ = [
        "#####",
        "#...#",
        "#...#",
        "#...#",
        "#####",
    ]
    rows = occupancy_to_thin_walls(occ, keep_frame=False)
    # Open sides become borders: floor east of the west wall → right border.
    assert rows[1][0] == "┤"
    assert rows[1][4] == "├"
    assert rows[0][2] == "┴"
    assert rows[4][2] == "┬"
    assert rows[2][2] == "."
    legend = thin_wall_legend(rows)
    assert legend["┤"]["type"] == "stone_wall_r"
    assert legend["┴"]["type"] == "stone_wall_b"


def test_occupancy_partition_and_door() -> None:
    from natural20.map_import.thin_wall import occupancy_to_thin_walls, punch_single_cell_doors

    occ = [
        "#######",
        "#.....#",
        "#######",
        "#.....#",
        "#######",
    ]
    with_door = punch_single_cell_doors(occ, min_room=3, keep_frame=True)
    assert with_door[2].count("-") == 1
    thinned = occupancy_to_thin_walls(occ, keep_frame=True)
    assert "Z" in thinned[2]


def test_occupancy_keeps_thick_masonry() -> None:
    from natural20.map_import.thin_wall import occupancy_to_thin_walls

    occ = [
        "......",
        ".####.",
        ".####.",
        ".####.",
        "......",
    ]
    rows = occupancy_to_thin_walls(occ, keep_frame=False)
    assert rows[2][2] == "#"
    assert rows[2][3] == "#"


def test_seed_grid_from_base_directional() -> None:
    from natural20.map_import.seed import seed_grid_from_base

    grid = ClassificationGrid(3, 3)
    written = seed_grid_from_base(grid, ["┌┬┐", "├.┤", "└┴┘"])
    assert written == 9
    assert grid.tiles[0][0].tile_class == "wall"
    assert grid.tiles[0][0].edges.N and grid.tiles[0][0].edges.W
    assert grid.tiles[1][1].tile_class == "floor"
    assert grid.tiles[1][0].edges.N


def test_region_verify_lists_every_square() -> None:
    from natural20.map_import.region_verify import verify_adventure_regions
    from natural20.map_import.vlm import MockClient

    grid = ClassificationGrid(4, 4)
    for y in range(4):
        for x in range(4):
            cls = "wall" if x in {0, 3} or y in {0, 3} else "floor"
            grid.set(TileRecord(x=x, y=y, tile_class=cls, confidence=0.8, source="occupancy"))
    anns = [
        {
            "id": "e5a",
            "label": "Hall",
            "map_key": "a",
            "kind": "area",
            "bounds": {"x1": 1, "y1": 1, "x2": 2, "y2": 2},
        }
    ]
    report = verify_adventure_regions(
        grid,
        "#### E5a. Hall\n\nTen-foot hall with four doors.\n",
        MockClient(),
        annotations=anns,
    )
    assert report["applied"] is True
    assert report["squares_listed"] == 16
    assert report["tile_fixes"] == 0


def test_region_verify_skips_duplicate_map_keys() -> None:
    from natural20.map_import.region_verify import verify_adventure_regions
    from natural20.map_import.vlm import MockClient

    grid = ClassificationGrid(3, 3)
    for y in range(3):
        for x in range(3):
            grid.set(TileRecord(x=x, y=y, tile_class="floor", confidence=0.8, source="occupancy"))
    anns = [
        {"id": "e5a", "label": "Hall", "map_key": "a", "kind": "area", "bounds": {"x1": 0, "y1": 0, "x2": 1, "y2": 1}},
        {"id": "a", "label": "Hall flood", "map_key": "a", "kind": "area", "bounds": {"x1": 0, "y1": 0, "x2": 2, "y2": 2}},
    ]
    report = verify_adventure_regions(
        grid,
        "#### E5a. Hall\n\nTen-foot hall.\n",
        MockClient(),
        annotations=anns,
    )
    ids = [r["id"] for r in report["region_reports"]]
    assert ids.count("E5a") == 1 or ids.count("e5a") == 1
    assert "a" not in ids


def test_accept_vlm_override_keeps_occupancy_walls() -> None:
    from natural20.map_import.classify import _accept_vlm_override

    assert _accept_vlm_override("wall", "floor", {"walls": {"N": True}}, 0.95, threshold=0.55) is False
    assert _accept_vlm_override("wall", "door", {"doors": {"N": True}}, 0.9, threshold=0.55) is True
    assert _accept_vlm_override("floor", "object", {}, 0.8, threshold=0.55) is True
    assert _accept_vlm_override("wall", "floor", {"walls": {}, "doors": {}}, 0.9, threshold=0.55) is True
    assert _accept_vlm_override("wall", "wall", {"doors": {"N": True}}, 0.95, threshold=0.55) is False


def test_consistency_does_not_rewrite_occupancy_class() -> None:
    from natural20.map_import.consistency import apply_consistency_rules
    from natural20.map_import.ink import EdgeBits

    grid = ClassificationGrid(3, 3)
    for y in range(3):
        for x in range(3):
            cls = "wall" if x == 1 and y == 1 else "floor"
            edges = EdgeBits(door_N=True) if cls == "wall" else EdgeBits()
            grid.set(
                TileRecord(
                    x=x,
                    y=y,
                    tile_class=cls,
                    confidence=0.9,
                    source="occupancy",
                    edges=edges,
                    flags=["occupancy"],
                )
            )
    apply_consistency_rules(grid)
    assert grid.tiles[1][1].tile_class == "wall"


def test_detect_ink_edges_and_directional_mapping() -> None:
    img = Image.new("RGB", (48, 48), (230, 220, 200))
    draw = ImageDraw.Draw(img)
    draw.line([(0, 0), (47, 0)], fill=(10, 10, 10), width=3)
    draw.line([(0, 0), (0, 47)], fill=(10, 10, 10), width=3)
    bits = detect_ink_edges(img)
    assert bits.N and bits.W
    assert not bits.solid
    assert mapping_for("wall", edges=bits).base_token == "┌"
    assert mapping_for("wall").base_token == "#"


def test_json_repair_truncated_overlay() -> None:
    truncated = '{"fixes": [{"x": 1, "y": 2, "class": "floor", "reason": "open'
    data = parse_json_object(truncated)
    assert data["fixes"][0]["x"] == 1
    assert data["fixes"][0]["class"] == "floor"


def test_heuristic_thin_wall_floorplan(tmp_path: Path) -> None:
    image = _paint_thin_room(tmp_path / "floorplan_6x6.png")
    knobs = ImportKnobs(
        image=str(image),
        width=6,
        height=6,
        provider="heuristic",
        name="Thin Room",
        calibrate_grid=False,
    )
    result = import_battlemap(knobs, workdir=tmp_path / "work", output=tmp_path / "thin.yml")
    base = result.properties["map"]["base"]
    joined = "\n".join(base)
    assert any(ch in joined for ch in "┌┐└┘├┤┬┴")
    assert "┌" in result.properties["legend"]
    assert result.properties["legend"]["┌"]["type"] == "stone_wall_tl"
    interior = result.grid.tiles[2][2]
    assert interior.tile_class == "floor"
    corner = result.grid.tiles[1][1]
    assert corner.tile_class in {"wall", "door"}
    assert corner.edges.any_wall()


def test_compare_occupancy_metrics() -> None:
    gold = {
        "map": {"base": ["#.#", "#-#", "###"]},
        "legend": {},
    }
    generated = {
        "map": {"base": ["┌.┐", "#-#", "└.┘"]},
        "legend": {
            "┌": {"type": "stone_wall_tl"},
            "┐": {"type": "stone_wall_tr"},
            "└": {"type": "stone_wall_bl"},
            "┘": {"type": "stone_wall_br"},
        },
    }
    report = compare_map_properties(gold, generated)
    assert report["gold_walls"] == 7
    assert report["generated_walls"] == 6
    assert report["door_recall"] == 1.0
    assert report["occupancy_iou"] > 0.7


def test_consistency_keeps_ink_walls() -> None:
    grid = ClassificationGrid(5, 5)
    for y in range(5):
        for x in range(5):
            grid.set(TileRecord(x=x, y=y, tile_class="floor", confidence=0.9, source="test"))
    bits = EdgeBits(N=True, W=True, scores={"N": 0.8, "W": 0.8})
    grid.set(
        TileRecord(
            x=2,
            y=2,
            tile_class="wall",
            confidence=0.4,
            source="test",
            edges=bits,
        )
    )
    apply_consistency_rules(grid)
    assert grid.tiles[2][2].tile_class == "wall"


def _draw_faint_grid(draw: ImageDraw.ImageDraw, width: int, height: int, tile: int) -> None:
    color = (168, 162, 150)
    for x in range(0, width + 1, tile):
        draw.line([(x, 0), (x, height)], fill=color, width=1)
    for y in range(0, height + 1, tile):
        draw.line([(0, y), (width, y)], fill=color, width=1)


def _paint_two_up(path: Path, tile: int = 20) -> Path:
    """Two 5x5 rooms side by side, separated by a thin full-height ink rule."""
    left_w, right_w, height = 5, 5, 5
    gutter = 14
    rule = 2
    img = Image.new(
        "RGB",
        (left_w * tile + gutter + right_w * tile, height * tile),
        (210, 200, 185),
    )
    draw = ImageDraw.Draw(img)
    _draw_faint_grid(draw, img.size[0], img.size[1], tile)

    def fill_room(ox: int) -> None:
        for y in range(height):
            for x in range(5):
                if x in {0, 4} or y in {0, 4}:
                    draw.rectangle(
                        [ox + x * tile, y * tile, ox + (x + 1) * tile - 1, (y + 1) * tile - 1],
                        fill=(12, 10, 9),
                    )

    fill_room(0)
    rx = left_w * tile + gutter // 2 - rule // 2
    draw.rectangle([rx, 0, rx + rule - 1, img.size[1] - 1], fill=(8, 8, 8))
    fill_room(left_w * tile + gutter)
    img.save(path)
    return path


def test_detect_two_up_panels(tmp_path: Path) -> None:
    from natural20.map_import.panels import detect_map_panels

    image = Image.open(_paint_two_up(tmp_path / "two_up.png"))
    panels = detect_map_panels(image, split=True)
    assert len(panels) == 2
    left, right = panels
    assert left.box[2] <= right.box[0] + 6
    assert left.box[2] - left.box[0] > 40
    assert right.box[2] - right.box[0] > 40


def test_single_room_is_one_panel(tmp_path: Path) -> None:
    from natural20.map_import.panels import detect_map_panels

    image = Image.open(_paint_room(tmp_path / "solo.png"))
    panels = detect_map_panels(image, split=True)
    assert len(panels) == 1


def test_import_splits_two_up_page(tmp_path: Path) -> None:
    from natural20.map_import import ImportBundle

    image = _paint_two_up(tmp_path / "halls.png")
    knobs = ImportKnobs(
        image=str(image),
        provider="heuristic",
        name="Halls",
        calibrate_grid=False,
        split_panels=True,
        tile_size=20,
    )
    result = import_battlemap(knobs, workdir=tmp_path / "work", output=tmp_path / "out.yml")
    assert isinstance(result, ImportBundle)
    assert len(result.results) == 2
    assert (tmp_path / "out_left.yml").is_file()
    assert (tmp_path / "out_right.yml").is_file()
    assert (tmp_path / "work" / "panels.json").is_file()


def test_auto_grid_without_filename_dims(tmp_path: Path) -> None:
    image = _paint_room(tmp_path / "plain.png", width=8, height=6, tile=16)
    img = Image.open(image)
    _draw_faint_grid(ImageDraw.Draw(img), img.size[0], img.size[1], 16)
    img.save(image)
    knobs = ImportKnobs(
        image=str(image),
        provider="heuristic",
        name="Plain",
        calibrate_grid=False,
        split_panels=False,
    )
    result = import_battlemap(knobs, workdir=tmp_path / "work", output=tmp_path / "plain.yml")
    assert result.spec.width >= 6
    assert result.spec.height >= 4
    assert result.spec.source.startswith("auto_grid")


def test_published_two_up_references_if_present() -> None:
    from natural20.map_import.panels import detect_map_panels

    church = REPO / "user_levels/death_house/references/chapter_3/map-03.02-church.jpg"
    coffin = REPO / "user_levels/death_house/references/chapter_5/map-05.05-coffin-makers-shop.png"
    if not church.is_file() or not coffin.is_file():
        return
    church_panels = detect_map_panels(Image.open(church), split=True)
    coffin_panels = detect_map_panels(Image.open(coffin), split=True)
    assert len(church_panels) == 2
    assert len(coffin_panels) == 2
    death = REPO / "user_levels/death_house/references/appendix_b/map-18.01-death-house.jpg"
    if death.is_file():
        death_panels = detect_map_panels(Image.open(death), split=True)
        # Front view dropped (no grid / header art); four house floors + dungeon remain.
        assert len(death_panels) == 5
        widths = [p.box[2] - p.box[0] for p in death_panels]
        heights = [p.box[3] - p.box[1] for p in death_panels]
        assert max(heights) > 1.4 * min(heights)
        assert max(widths) < 0.85 * Image.open(death).size[0]


def _font():
    for path in (
        "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).is_file():
            from PIL import ImageFont

            return ImageFont.truetype(path, 22)
    from PIL import ImageFont

    return ImageFont.load_default()


def _paint_keyed_hall(path: Path, *, tile: int = 32) -> Path:
    """Interior hall with a title, compass, and circled room key 'a'."""
    width, height = 10, 8
    img = Image.new("RGB", (width * tile, height * tile), (210, 200, 180))
    draw = ImageDraw.Draw(img)
    wall = (12, 10, 9)
    for x in range(width):
        draw.rectangle([x * tile, 0, (x + 1) * tile - 1, tile - 1], fill=wall)
        draw.rectangle([x * tile, (height - 1) * tile, (x + 1) * tile - 1, height * tile - 1], fill=wall)
    for y in range(height):
        draw.rectangle([0, y * tile, tile - 1, (y + 1) * tile - 1], fill=wall)
        draw.rectangle([(width - 1) * tile, y * tile, width * tile - 1, (y + 1) * tile - 1], fill=wall)
    font = _font()
    # Title on interior floor (dark ink on parchment), not on the wall fill.
    draw.text((tile + 6, tile + 4), "Ground Floor", fill=(8, 8, 8), font=font)
    # Compass ~2.5 tiles across so radial-ink detection can fire.
    cx, cy = int(7.2 * tile), int(5.2 * tile)
    draw.ellipse([cx - 36, cy - 36, cx + 36, cy + 36], outline=wall, width=3)
    import math

    for angle in (0, 45, 90, 135, 180, 225, 270, 315):
        rad = math.radians(angle)
        draw.line([(cx, cy), (cx + int(34 * math.cos(rad)), cy + int(34 * math.sin(rad)))], fill=wall, width=3)
    draw.text((cx - 6, cy - 48), "N", fill=wall, font=font)
    # Circled key 'a' in the room center.
    kx, ky = int(4.5 * tile), int(3.5 * tile)
    draw.ellipse([kx - 14, ky - 14, kx + 14, ky + 16], fill=(40, 18, 12))  # drop shadow
    draw.ellipse([kx - 16, ky - 16, kx + 16, ky + 16], fill=(245, 245, 240), outline=wall, width=2)
    draw.text((kx - 6, ky - 10), "a", fill=wall, font=font)
    img.save(path)
    return path


def test_parse_keyed_adventure_headings() -> None:
    from natural20.map_import.adventure import letter_from_code, parse_keyed_areas

    text = """
#### E5a. Hall
The doors open to a mildewed hall.

#### E5f. Chapel
Donavich (LG male human **acolyte**) kneels at the altar.

#### E5g. Undercroft
A **vampire spawn** waits by a moldy chest.
"""
    areas = parse_keyed_areas(text)
    assert [a.letter for a in areas] == ["a", "f", "g"]
    assert letter_from_code("E5a") == "a"
    assert letter_from_code("B") == "b"
    chapel = next(a for a in areas if a.letter == "f")
    assert "acolyte" in chapel.body


def test_overlays_mask_title_compass_and_match_key(tmp_path: Path) -> None:
    image = _paint_keyed_hall(tmp_path / "keyed_10x8.png")
    knobs = ImportKnobs(
        image=str(image),
        width=10,
        height=8,
        provider="heuristic",
        name="Keyed Hall",
        calibrate_grid=False,
        split_panels=False,
        adventure_text=(
            "#### E1a. Guard post\n"
            "A **goblin** stands in this hall. A wooden chest sits against the wall.\n"
        ),
    )
    result = import_battlemap(knobs, workdir=tmp_path / "work", output=tmp_path / "keyed.yml")
    overlay_kinds = {m["kind"] for m in (result.overlay_report.get("marks") or [])}
    letters = {m["text"] for m in (result.overlay_report.get("marks") or []) if m.get("kind") == "key"}
    assert "a" in letters
    assert "title" in overlay_kinds or "caption" in overlay_kinds
    # Title on the north wall row must not remain a wall solely because of glyph ink —
    # the outer frame is still a wall; the circled key tile must be walkable.
    key_marks = [m for m in result.overlay_report["marks"] if m["kind"] == "key"]
    assert key_marks
    key_tiles = [tuple(t) for t in key_marks[0]["tiles"]]
    walkable = {".", "-", "|"}
    base = result.properties["map"]["base"]
    assert any(base[y][x] in walkable for x, y in key_tiles)
    anns = result.properties.get("map_annotations") or []
    assert any(a.get("map_key") == "a" or "guard" in str(a.get("label") or "").lower() for a in anns)
    legend = result.properties.get("legend") or {}
    assert any(v.get("sub_type") == "goblin" for v in legend.values() if isinstance(v, dict))
    assert any(v.get("type") == "chest" for v in legend.values() if isinstance(v, dict))


def test_detect_church_keys_if_present() -> None:
    from natural20.map_import.dimensions import infer_grid_spec
    from natural20.map_import.overlays import detect_overlays

    church = REPO / "user_levels/death_house/references/chapter_3/map-03.02-church.jpg"
    if not church.is_file():
        return
    image = Image.open(church)
    spec = infer_grid_spec(church, tile_size=44, image=image)
    report = detect_overlays(image, spec, prefer_letters=set("abcdefg"))
    letters = {m.text for m in report.keys()}
    assert {"a", "b", "c", "d", "e", "f", "g"} <= letters
    kinds = {m.kind for m in report.marks}
    assert "title" in kinds or "caption" in kinds
    assert "compass" in kinds or "scale" in kinds

