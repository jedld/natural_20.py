"""Procedural tile textures and object icons for map rendering."""

from __future__ import annotations

import hashlib
import math
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

COLOR_NAME_TO_HEX = {
    "black": "#111111",
    "white": "#f2f2f2",
    "red": "#b33a3a",
    "green": "#3a8f4a",
    "blue": "#3a5fb3",
    "yellow": "#c9b23a",
    "brown": "#7a5a3a",
    "cyan": "#3a9aa8",
    "magenta": "#a83a8f",
    "orange": "#c97a2a",
    "purple": "#6a3a9a",
    "gray": "#6a6a6a",
    "grey": "#6a6a6a",
}

# Theme definitions: floor, wall, accent, water, fog, door wood
# Colors are intentionally exaggerated so maps read differently at a glance.
THEME_PALETTES: dict[str, dict[str, tuple[str, ...]]] = {
    "stone": {
        "floor": ("#7a756c", "#6a655c", "#8a857c", "#5a554c"),
        "mortar": ("#3a3630",),
        "wall": ("#4a4a58", "#5a5a6a", "#3a3a48"),
        "wall_edge": ("#8a8a9a", "#1c1c28"),
        "water": ("#2a5f8a", "#3a7faa"),
        "fog": ("#3a3a4a",),
        "door": ("#6b4423", "#2a2018"),
        "accent": ("#c9a84a",),
    },
    "cobble": {
        "floor": ("#8a7a68", "#7a6a58", "#9a8a78", "#6a5a48", "#a09080"),
        "mortar": ("#3a3028",),
        "wall": ("#6a5a4a", "#7a6a5a", "#5a4a3a"),
        "wall_edge": ("#b0a090", "#2a2018"),
        "water": ("#3a6a8a", "#4a8aaa"),
        "fog": ("#5a4a3a",),
        "door": ("#5a3a1a", "#1e140c"),
        "accent": ("#e0b050",),
    },
    "dirt": {
        "floor": ("#8b5f2d", "#7a4f24", "#9a6d36", "#6a3f1c"),
        "mortar": ("#3a2818",),
        "wall": ("#5a4030", "#6a5040", "#4a3020"),
        "wall_edge": ("#9a7a5a", "#1a1208"),
        "water": ("#2a5a4a", "#3a7a6a"),
        "fog": ("#4a3a2a",),
        "door": ("#5a3a18", "#1e1408"),
        "accent": ("#c09040",),
    },
    "grass": {
        "floor": ("#3f8b34", "#35802c", "#4a9a3d", "#2e7028", "#5aaa45"),
        "mortar": ("#2a5020",),
        "wall": ("#6a6a52", "#7a7a62", "#5a5a42"),
        "wall_edge": ("#9a9a82", "#1a1a14"),
        "water": ("#2a8f9a", "#3aafbf"),
        "fog": ("#3a6a3a",),
        "door": ("#5a3a18", "#1e1408"),
        "accent": ("#90da50",),
    },
    "cathedral": {
        "floor": ("#6a5a78", "#5a4a68", "#7a6a88", "#4a3a58", "#8a7a98"),
        "mortar": ("#2a1840",),
        "wall": ("#4a3060", "#5a4070", "#3a2050"),
        "wall_edge": ("#d0b060", "#1a0830"),
        "water": ("#2a306a", "#4a50aa"),
        "fog": ("#2a1840",),
        "door": ("#5a2818", "#1a0e08"),
        "accent": ("#e8c860", "#c05070"),
    },
    "sewer": {
        "floor": ("#2a5040", "#1e4034", "#346050", "#183828", "#3a6858"),
        "mortar": ("#0e2018",),
        "wall": ("#1a3830", "#2a4840", "#122820"),
        "wall_edge": ("#4a8870", "#061410"),
        "water": ("#1a6040", "#2a8858", "#145038"),
        "fog": ("#102820",),
        "door": ("#3a2a1a", "#120c08"),
        "accent": ("#60c050", "#8a4030"),
    },
    "prison": {
        "floor": ("#4a5060", "#3a4050", "#5a6070", "#2e3444"),
        "mortar": ("#121820",),
        "wall": ("#2a3040", "#3a4050", "#1a2030"),
        "wall_edge": ("#8090a8", "#080c14"),
        "water": ("#203850", "#305870"),
        "fog": ("#181c28",),
        "door": ("#3a2a1a", "#120c08"),
        "accent": ("#a08040", "#6080a0"),
    },
    "manor": {
        "floor": ("#8a5a38", "#7a4a28", "#9a6a48", "#6a3a18", "#aa7a58"),
        "mortar": ("#3a1c10",),
        "wall": ("#5a3028", "#6a4038", "#4a2018"),
        "wall_edge": ("#d0a070", "#1a0808"),
        "water": ("#2a5a6a", "#3a7a8a"),
        "fog": ("#3a2018",),
        "door": ("#6a3a18", "#1e1208"),
        "accent": ("#e0b060", "#a04050"),
    },
    "street": {
        "floor": ("#4a4858", "#3a3848", "#5a5868", "#2e2c3c", "#6a6878"),
        "mortar": ("#14121c",),
        "wall": ("#3a3440", "#4a4450", "#2a2430"),
        "wall_edge": ("#e0a050", "#100e18"),
        "water": ("#1a3050", "#2a5080"),
        "fog": ("#1a1828",),
        "door": ("#5a3a1a", "#1e1208"),
        "accent": ("#f0b040", "#806040"),
    },
    "tavern": {
        "floor": ("#a07040", "#906030", "#b08050", "#805020", "#c09060"),
        "mortar": ("#402010",),
        "wall": ("#603828", "#704838", "#502818"),
        "wall_edge": ("#e0c080", "#201008"),
        "water": ("#6a4020", "#8a6030"),
        "fog": ("#402818",),
        "door": ("#704018", "#201008"),
        "accent": ("#f0c050", "#d05030"),
    },
    "docks": {
        "floor": ("#4a6070", "#3a5060", "#5a7080", "#2a4050", "#6a8090"),
        "mortar": ("#182028",),
        "wall": ("#3a4850", "#4a5860", "#2a3840"),
        "wall_edge": ("#90b0c0", "#0e1418"),
        "water": ("#104060", "#186080", "#0c3050"),
        "fog": ("#183040",),
        "door": ("#4a3828", "#181008"),
        "accent": ("#c09050", "#4080a0"),
    },
}



def parse_color(value: str | None, *, fallback: str = "#888888") -> tuple[int, int, int, int]:
    if not value:
        value = fallback
    value = str(value).strip()
    if value.startswith("#"):
        hex_value = value[1:]
        if len(hex_value) == 3:
            hex_value = "".join(ch * 2 for ch in hex_value)
        if len(hex_value) == 6:
            r = int(hex_value[0:2], 16)
            g = int(hex_value[2:4], 16)
            b = int(hex_value[4:6], 16)
            return r, g, b, 255
        if len(hex_value) == 8:
            r = int(hex_value[0:2], 16)
            g = int(hex_value[2:4], 16)
            b = int(hex_value[4:6], 16)
            a = int(hex_value[6:8], 16)
            return r, g, b, a
    lowered = value.lower()
    if lowered in COLOR_NAME_TO_HEX:
        return parse_color(COLOR_NAME_TO_HEX[lowered])
    return parse_color(fallback)


def blend(a: tuple[int, int, int, int], b: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
        int(a[3] + (b[3] - a[3]) * t),
    )


def shade(color: tuple[int, int, int, int], amount: float) -> tuple[int, int, int, int]:
    """amount > 0 lightens, < 0 darkens."""
    if amount >= 0:
        return blend(color, (255, 255, 255, color[3]), amount)
    return blend(color, (0, 0, 0, color[3]), -amount)


def theme_for_name(name: str = "", description: str = "", map_id: str = "") -> str:
    """Infer a theme palette from map metadata."""
    text = f"{map_id} {name} {description}".lower()
    rules = [
        (("sewer", "undercity", "drain", "muck"), "sewer"),
        (("cathedral", "church", "temple", "chapel", "altar"), "cathedral"),
        (("prison", "dungeon", "cell", "jail"), "prison"),
        (("tavern", "inn", "pub", "alehouse"), "tavern"),
        (("dock", "harbor", "wharf", "pier", "quay", "riverfront"), "docks"),
        (("manor", "mansion", "estate", "reed"), "manor"),
        (("street", "road", "alley", "plaza", "gate", "city"), "street"),
        (("cobble", "market"), "cobble"),
        (("cave", "cavern", "mine", "goblin"), "dirt"),
        (("forest", "grove", "garden", "meadow"), "grass"),
        (("water", "harbor", "dock", "river"), "docks"),
    ]
    for keywords, theme in rules:
        if any(word in text for word in keywords):
            return theme
    return "stone"


def get_theme(palette: str) -> dict[str, tuple[str, ...]]:
    return THEME_PALETTES.get(palette, THEME_PALETTES["stone"])


def _seed_for(x: int, y: int, salt: str = "") -> int:
    digest = hashlib.md5(f"{x}:{y}:{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _pick(rng: random.Random, colors: tuple[str, ...]) -> tuple[int, int, int, int]:
    return parse_color(rng.choice(colors))


def _noise_speckles(
    draw: ImageDraw.ImageDraw,
    tile_size: int,
    rng: random.Random,
    colors: tuple[str, ...],
    density: float = 0.08,
) -> None:
    count = int(tile_size * tile_size * density)
    for _ in range(count):
        x = rng.randint(0, tile_size - 1)
        y = rng.randint(0, tile_size - 1)
        color = shade(_pick(rng, colors), rng.uniform(-0.2, 0.2))
        draw.point((x, y), fill=color)


def _maybe_gen_tile(surface: str, tile_size: int, palette: str, seed: int) -> Image.Image | None:
    """Return a tile sampled from an MCP texture pack when available."""
    try:
        from natural20.map_image.gen_textures import load_texture, sample_texture
    except Exception:
        return None
    atlas = load_texture(palette, surface)
    if atlas is None:
        return None
    return sample_texture(atlas, tile_size, seed)


@lru_cache(maxsize=256)
def floor_tile(tile_size: int, palette: str, seed: int) -> Image.Image:
    generated = _maybe_gen_tile("floor", tile_size, palette, seed)
    if generated is not None:
        return generated
    theme = get_theme(palette)
    rng = random.Random(seed)
    floors = theme["floor"]
    mortar = theme["mortar"][0]

    if palette in {"cathedral"}:
        return _floor_flagstone(tile_size, floors, mortar, rng)
    if palette in {"manor", "tavern"}:
        return _floor_wood(tile_size, floors, mortar, rng)
    if palette in {"street", "cobble"}:
        return _floor_cobble(tile_size, floors, mortar, rng)
    if palette == "prison":
        return _floor_prison(tile_size, floors, mortar, rng)
    if palette == "sewer":
        return _floor_sewer(tile_size, floors, mortar, theme["water"], rng)
    if palette == "docks":
        return _floor_docks(tile_size, floors, mortar, theme["water"], rng)
    if palette == "grass":
        return _floor_grass(tile_size, floors, rng)
    if palette == "dirt":
        return _floor_dirt(tile_size, floors, rng)
    return _floor_flagstone(tile_size, floors, mortar, rng)


def _floor_flagstone(
    tile_size: int,
    floors: tuple[str, ...],
    mortar: str,
    rng: random.Random,
) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), parse_color(mortar))
    draw = ImageDraw.Draw(image)
    gap = max(1, tile_size // 32)
    # Irregular 2x2 or 3x2 flagstones
    cols = 2 if tile_size < 48 else 3
    rows = 2
    cell_w = tile_size // cols
    cell_h = tile_size // rows
    for row in range(rows):
        offset = (cell_w // 2) if row % 2 else 0
        for col in range(cols + 1):
            x0 = col * cell_w - offset + gap
            y0 = row * cell_h + gap
            x1 = x0 + cell_w - gap * 2
            y1 = y0 + cell_h - gap * 2
            if x1 <= 0 or y1 <= 0 or x0 >= tile_size:
                continue
            x0 = max(0, x0)
            y0 = max(0, y0)
            x1 = min(tile_size - 1, x1)
            y1 = min(tile_size - 1, y1)
            fill = shade(_pick(rng, floors), rng.uniform(-0.08, 0.08))
            draw.rectangle([x0, y0, x1, y1], fill=fill)
            # Edge highlight / shadow
            draw.line([(x0, y0), (x1, y0)], fill=shade(fill, 0.18), width=1)
            draw.line([(x0, y1), (x1, y1)], fill=shade(fill, -0.22), width=1)
    _noise_speckles(draw, tile_size, rng, floors, density=0.04)
    return image


def _floor_cobble(
    tile_size: int,
    floors: tuple[str, ...],
    mortar: str,
    rng: random.Random,
) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), parse_color(mortar))
    draw = ImageDraw.Draw(image)
    stone_w = max(6, tile_size // 5)
    stone_h = max(4, tile_size // 6)
    y = 1
    row = 0
    while y < tile_size:
        x = -(stone_w // 2) if row % 2 else 0
        while x < tile_size:
            jitter = rng.randint(-1, 1)
            x0 = x + jitter
            y0 = y + rng.randint(-1, 1)
            x1 = min(tile_size - 1, x0 + stone_w - 2)
            y1 = min(tile_size - 1, y0 + stone_h - 2)
            if x1 > x0 and y1 > y0:
                fill = shade(_pick(rng, floors), rng.uniform(-0.12, 0.12))
                draw.ellipse([x0, y0, x1, y1], fill=fill)
                draw.arc([x0, y0, x1, y1], 200, 340, fill=shade(fill, 0.2))
            x += stone_w
        y += stone_h - 1
        row += 1
    _noise_speckles(draw, tile_size, rng, floors, density=0.03)
    return image


def _floor_sewer(
    tile_size: int,
    floors: tuple[str, ...],
    mortar: str,
    water: tuple[str, ...],
    rng: random.Random,
) -> Image.Image:
    # Wet flagstones with slime pooling — distinct from brick walls
    image = Image.new("RGBA", (tile_size, tile_size), parse_color(mortar))
    draw = ImageDraw.Draw(image)
    gap = max(1, tile_size // 24)
    cols, rows = 2, 2
    cell_w = tile_size // cols
    cell_h = tile_size // rows
    for row in range(rows):
        for col in range(cols):
            x0 = col * cell_w + gap
            y0 = row * cell_h + gap
            x1 = (col + 1) * cell_w - gap
            y1 = (row + 1) * cell_h - gap
            fill = shade(_pick(rng, floors), rng.uniform(-0.12, 0.08))
            draw.rectangle([x0, y0, x1, y1], fill=fill)
            draw.line([(x0, y0), (x1, y0)], fill=shade(fill, 0.12), width=1)
            draw.line([(x0, y1), (x1, y1)], fill=shade(fill, -0.25), width=1)
            # Wet sheen on some stones
            if rng.random() < 0.45:
                wet = parse_color(rng.choice(water))[:3] + (55,)
                draw.ellipse(
                    [x0 + 2, y0 + 2, x1 - 2, y1 - max(2, (y1 - y0) // 2)],
                    fill=wet,
                )
    # Occasional slime drip
    for _ in range(rng.randint(1, 3)):
        x = rng.randint(2, tile_size - 3)
        y = rng.randint(2, tile_size - 3)
        draw.ellipse([x, y, x + 2, y + 3], fill=parse_color(water[0])[:3] + (100,))
    return image


def _floor_grass(tile_size: int, floors: tuple[str, ...], rng: random.Random) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), _pick(rng, floors))
    draw = ImageDraw.Draw(image)
    for _ in range(tile_size * 2):
        x = rng.randint(0, tile_size - 1)
        y = rng.randint(0, tile_size - 1)
        h = rng.randint(2, max(3, tile_size // 6))
        color = shade(_pick(rng, floors), rng.uniform(-0.15, 0.25))
        draw.line([(x, y + h), (x + rng.randint(-1, 1), y)], fill=color, width=1)
    return image


def _floor_dirt(tile_size: int, floors: tuple[str, ...], rng: random.Random) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), _pick(rng, floors))
    draw = ImageDraw.Draw(image)
    for _ in range(tile_size):
        x = rng.randint(0, tile_size - 1)
        y = rng.randint(0, tile_size - 1)
        r = rng.randint(1, max(2, tile_size // 12))
        color = shade(_pick(rng, floors), rng.uniform(-0.2, 0.15))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    return image


def _floor_wood(
    tile_size: int,
    floors: tuple[str, ...],
    mortar: str,
    rng: random.Random,
) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), parse_color(mortar))
    draw = ImageDraw.Draw(image)
    plank_h = max(4, tile_size // 4)
    y = 0
    while y < tile_size:
        fill = shade(_pick(rng, floors), rng.uniform(-0.1, 0.12))
        draw.rectangle([0, y, tile_size - 1, min(tile_size - 1, y + plank_h - 2)], fill=fill)
        draw.line([(0, y), (tile_size, y)], fill=shade(fill, 0.2), width=1)
        draw.line(
            [(0, y + plank_h - 2), (tile_size, y + plank_h - 2)],
            fill=shade(fill, -0.25),
            width=1,
        )
        # Grain
        for _ in range(max(2, tile_size // 10)):
            x0 = rng.randint(1, tile_size - 2)
            draw.line(
                [(x0, y + 1), (x0 + rng.randint(4, tile_size // 3), y + plank_h - 3)],
                fill=shade(fill, rng.uniform(-0.15, 0.1))[:3] + (90,),
                width=1,
            )
        y += plank_h
    return image


def _floor_prison(
    tile_size: int,
    floors: tuple[str, ...],
    mortar: str,
    rng: random.Random,
) -> Image.Image:
    # Large cold slabs — distinct from oval cobbles
    image = Image.new("RGBA", (tile_size, tile_size), parse_color(mortar))
    draw = ImageDraw.Draw(image)
    gap = max(1, tile_size // 28)
    for row in range(2):
        for col in range(2):
            x0 = col * (tile_size // 2) + gap
            y0 = row * (tile_size // 2) + gap
            x1 = (col + 1) * (tile_size // 2) - gap
            y1 = (row + 1) * (tile_size // 2) - gap
            fill = shade(_pick(rng, floors), rng.uniform(-0.1, 0.05))
            draw.rectangle([x0, y0, x1, y1], fill=fill)
            draw.rectangle([x0, y0, x1, y1], outline=shade(fill, -0.3))
            if rng.random() < 0.35:
                # Scratch marks
                sx = rng.randint(x0 + 2, max(x0 + 3, x1 - 4))
                draw.line([(sx, y0 + 2), (sx + 3, y1 - 2)], fill=shade(fill, -0.4), width=1)
    return image


def _floor_docks(
    tile_size: int,
    floors: tuple[str, ...],
    mortar: str,
    water: tuple[str, ...],
    rng: random.Random,
) -> Image.Image:
    image = _floor_wood(tile_size, floors, mortar, rng)
    draw = ImageDraw.Draw(image)
    # Wet patches / river spray
    for _ in range(rng.randint(2, 5)):
        x = rng.randint(1, tile_size - 4)
        y = rng.randint(1, tile_size - 4)
        wet = parse_color(rng.choice(water))[:3] + (70,)
        draw.ellipse([x, y, x + rng.randint(3, 8), y + rng.randint(2, 5)], fill=wet)
    return image


@lru_cache(maxsize=256)
def wall_tile(tile_size: int, mask: int, palette: str) -> Image.Image:
    """Solid filled wall with theme brick texture. mask unused for fill (kept for API)."""
    generated = _maybe_gen_tile("wall", tile_size, palette, hash((tile_size, mask, palette)) & 0xFFFFFFFF)
    if generated is not None:
        return generated
    theme = get_theme(palette)
    rng = random.Random(hash((tile_size, mask, palette)) & 0xFFFFFFFF)
    walls = theme["wall"]
    edges = theme["wall_edge"]
    image = Image.new("RGBA", (tile_size, tile_size), _pick(rng, walls))
    draw = ImageDraw.Draw(image)

    brick_h = max(4, tile_size // 4)
    brick_w = max(6, tile_size // 2)
    for row, y in enumerate(range(0, tile_size, brick_h)):
        offset = (brick_w // 2) if row % 2 else 0
        for x in range(-offset, tile_size + brick_w, brick_w):
            fill = shade(_pick(rng, walls), rng.uniform(-0.08, 0.08))
            draw.rectangle(
                [x, y, x + brick_w - 1, y + brick_h - 1],
                fill=fill,
                outline=parse_color(edges[-1] if len(edges) > 1 else "#1a1a1a"),
            )
            draw.line([(x, y), (x + brick_w - 1, y)], fill=parse_color(edges[0]), width=1)

    # Soft bevel on tile edges for depth
    edge = parse_color(edges[0])
    dark = parse_color(edges[-1] if len(edges) > 1 else "#111111")
    draw.line([(0, 0), (tile_size, 0)], fill=edge, width=1)
    draw.line([(0, 0), (0, tile_size)], fill=edge, width=1)
    draw.line([(0, tile_size - 1), (tile_size, tile_size - 1)], fill=dark, width=1)
    draw.line([(tile_size - 1, 0), (tile_size - 1, tile_size)], fill=dark, width=1)
    return image


@lru_cache(maxsize=128)
def water_tile(tile_size: int, seed: int, palette: str = "stone") -> Image.Image:
    generated = _maybe_gen_tile("water", tile_size, palette, seed)
    if generated is not None:
        return generated
    theme = get_theme(palette)
    waters = theme["water"]
    rng = random.Random(seed)
    image = Image.new("RGBA", (tile_size, tile_size), _pick(rng, waters))
    draw = ImageDraw.Draw(image)
    for i in range(max(3, tile_size // 6)):
        y = int((i + 0.5) * tile_size / max(3, tile_size // 6)) + rng.randint(-1, 1)
        color = shade(_pick(rng, waters), rng.uniform(-0.1, 0.25))
        amplitude = max(2, tile_size // 10)
        points = []
        for x in range(0, tile_size, 2):
            yy = y + int(math.sin(x / 4 + seed + i) * amplitude * 0.4)
            points.append((x, yy))
        if len(points) > 1:
            draw.line(points, fill=color[:3] + (180,), width=1)
    # Specular dots
    for _ in range(tile_size // 8):
        x = rng.randint(1, tile_size - 2)
        y = rng.randint(1, tile_size - 2)
        draw.point((x, y), fill=(220, 230, 240, 120))
    return image


@lru_cache(maxsize=64)
def door_tile(tile_size: int, orientation: str, palette: str = "stone") -> Image.Image:
    theme = get_theme(palette)
    image = floor_tile(tile_size, palette, 7).copy()
    draw = ImageDraw.Draw(image)
    wood = parse_color(theme["door"][0])
    frame = parse_color(theme["door"][-1] if len(theme["door"]) > 1 else "#2a2018")
    margin = max(3, tile_size // 8)
    if orientation in {"-", "horizontal"}:
        y0 = tile_size // 2 - tile_size // 5
        y1 = tile_size // 2 + tile_size // 5
        draw.rectangle([margin, y0, tile_size - margin, y1], fill=frame)
        draw.rectangle([margin + 2, y0 + 2, tile_size - margin - 2, y1 - 2], fill=wood)
        # Planks
        for x in range(margin + 4, tile_size - margin - 2, max(3, tile_size // 8)):
            draw.line([(x, y0 + 2), (x, y1 - 2)], fill=shade(wood, -0.2), width=1)
        # Handle
        hx = tile_size * 3 // 4
        hy = (y0 + y1) // 2
        draw.ellipse([hx - 2, hy - 2, hx + 2, hy + 2], fill=parse_color(theme["accent"][0]))
    else:
        x0 = tile_size // 2 - tile_size // 5
        x1 = tile_size // 2 + tile_size // 5
        draw.rectangle([x0, margin, x1, tile_size - margin], fill=frame)
        draw.rectangle([x0 + 2, margin + 2, x1 - 2, tile_size - margin - 2], fill=wood)
        for y in range(margin + 4, tile_size - margin - 2, max(3, tile_size // 8)):
            draw.line([(x0 + 2, y), (x1 - 2, y)], fill=shade(wood, -0.2), width=1)
        hx = (x0 + x1) // 2
        hy = tile_size * 3 // 4
        draw.ellipse([hx - 2, hy - 2, hx + 2, hy + 2], fill=parse_color(theme["accent"][0]))
    return image


@lru_cache(maxsize=256)
def marker_tile(tile_size: int, color: str, label: str) -> Image.Image:
    rgba = parse_color(color)
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = max(2, tile_size // 8)
    draw.ellipse(
        [margin, margin, tile_size - margin, tile_size - margin],
        fill=rgba,
        outline=(255, 255, 255, 220),
        width=max(1, tile_size // 24),
    )
    text = (label or "?")[:2].upper()
    try:
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            ((tile_size - tw) / 2, (tile_size - th) / 2),
            text,
            fill=(255, 255, 255, 240),
            font=font,
        )
    except Exception:
        pass
    return image


@lru_cache(maxsize=128)
def object_icon(tile_size: int, obj_type: str, palette: str = "stone", seed: int = 0) -> Image.Image | None:
    """Procedural icon for common object types when no sprite asset exists."""
    kind = (obj_type or "").lower().replace("-", "_")
    builders = {
        "teleporter": _icon_teleporter,
        "chest": _icon_chest,
        "barrel": _icon_barrel,
        "campfire": _icon_campfire,
        "fireplace": _icon_campfire,
        "pit_trap": _icon_pit,
        "note": _icon_note,
        "interactive_object": _icon_interactive,
        "symbol": _icon_symbol,
        "altar": _icon_altar,
        "candle": _icon_candle,
        "ritual_candle": _icon_candle,
        "brazier": _icon_campfire,
        "tree": _icon_tree,
        "briar": _icon_briar,
        "switch": _icon_switch,
        "difficult_terrain": _icon_difficult_terrain,
        "chasm": _icon_chasm,
        "spike_pit": _icon_pit,
        "wooden_door": lambda s, p, r: door_tile(s, "vertical", p),
        "door": lambda s, p, r: door_tile(s, "vertical", p),
        "water": lambda s, p, r: water_tile(s, r, p),
        "ground": lambda s, p, r: floor_tile(s, p, r),
        "stone_wall": lambda s, p, r: wall_tile(s, 0, p),
    }
    # Fuzzy match
    for key, builder in builders.items():
        if key in kind or kind in key:
            rng = random.Random(seed)
            return builder(tile_size, palette, rng.randint(0, 10_000))
    return None


def _icon_teleporter(tile_size: int, palette: str, seed: int) -> Image.Image:
    theme = get_theme(palette)
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cx = cy = tile_size // 2
    accent = parse_color(theme["accent"][0])
    blue = parse_color("#3a6fd4")
    for i, radius in enumerate(range(tile_size // 2 - 2, 2, -max(2, tile_size // 10))):
        color = blend(blue, accent, i / 5)[:3] + (200 - i * 20,)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=color, width=2)
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=accent)
    return image


def _icon_chest(tile_size: int, palette: str, seed: int) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    m = max(3, tile_size // 6)
    wood = parse_color("#8b5a2b")
    dark = shade(wood, -0.3)
    gold = parse_color("#c9a84a")
    draw.rounded_rectangle([m, m + 2, tile_size - m, tile_size - m], radius=2, fill=wood, outline=dark)
    draw.arc([m, m - 2, tile_size - m, m + tile_size // 3], 180, 0, fill=dark, width=2)
    draw.rectangle([m, m + tile_size // 5, tile_size - m, m + tile_size // 5 + 2], fill=dark)
    lx = tile_size // 2
    ly = tile_size // 2 + 1
    draw.rectangle([lx - 2, ly - 2, lx + 2, ly + 3], fill=gold)
    return image


def _icon_barrel(tile_size: int, palette: str, seed: int) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    m = max(4, tile_size // 5)
    wood = parse_color("#6b4f2d")
    band = parse_color("#3a3a3a")
    draw.ellipse([m, m // 2, tile_size - m, tile_size - m // 2], fill=wood, outline=shade(wood, -0.3))
    mid = tile_size // 2
    draw.line([(m + 1, mid - 2), (tile_size - m - 1, mid - 2)], fill=band, width=2)
    draw.line([(m + 1, mid + 2), (tile_size - m - 1, mid + 2)], fill=band, width=2)
    return image


def _icon_campfire(tile_size: int, palette: str, seed: int) -> Image.Image:
    rng = random.Random(seed)
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cx = tile_size // 2
    base = tile_size - max(4, tile_size // 6)
    # Logs
    draw.line([(cx - tile_size // 4, base), (cx + tile_size // 4, base - 2)], fill=parse_color("#4a2a10"), width=3)
    draw.line([(cx + tile_size // 4, base), (cx - tile_size // 4, base - 2)], fill=parse_color("#3a1a08"), width=3)
    # Flames
    for color, scale in (("#ff7a2b", 1.0), ("#ffcc33", 0.65), ("#fff0a0", 0.35)):
        h = int(tile_size * 0.45 * scale)
        w = int(tile_size * 0.28 * scale)
        draw.polygon(
            [(cx, base - h - rng.randint(0, 2)), (cx - w, base - 2), (cx + w, base - 2)],
            fill=parse_color(color),
        )
    return image


def _icon_pit(tile_size: int, palette: str, seed: int) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    m = max(2, tile_size // 10)
    draw.ellipse([m, m, tile_size - m, tile_size - m], fill=parse_color("#1a1a1a"), outline=parse_color("#4a3a2a"))
    # Spikes
    spike = parse_color("#8a8a8a")
    for i in range(3):
        x = tile_size // 4 + i * tile_size // 4
        draw.polygon([(x, tile_size // 2), (x - 3, tile_size * 3 // 4), (x + 3, tile_size * 3 // 4)], fill=spike)
    return image


def _icon_note(tile_size: int, palette: str, seed: int) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    m = max(4, tile_size // 5)
    paper = parse_color("#e8dcc0")
    ink = parse_color("#3a2a1a")
    draw.polygon(
        [(m, m), (tile_size - m, m), (tile_size - m, tile_size - m), (m, tile_size - m)],
        fill=paper,
        outline=shade(paper, -0.3),
    )
    # Folded corner
    draw.polygon(
        [(tile_size - m, m), (tile_size - m - tile_size // 6, m), (tile_size - m, m + tile_size // 6)],
        fill=shade(paper, -0.15),
    )
    for i in range(3):
        y = m + 4 + i * max(3, tile_size // 8)
        draw.line([(m + 3, y), (tile_size - m - 4, y)], fill=ink[:3] + (160,), width=1)
    return image


def _icon_interactive(tile_size: int, palette: str, seed: int) -> Image.Image:
    theme = get_theme(palette)
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    accent = parse_color(theme["accent"][0])
    m = max(3, tile_size // 6)
    draw.rounded_rectangle(
        [m, m, tile_size - m, tile_size - m],
        radius=max(2, tile_size // 10),
        fill=accent[:3] + (200,),
        outline=shade(accent, -0.3),
        width=2,
    )
    # Magnifying cue
    cx = cy = tile_size // 2
    r = tile_size // 6
    draw.ellipse([cx - r, cy - r - 1, cx + r, cy + r - 1], outline=(255, 255, 255, 220), width=2)
    draw.line([(cx + r - 1, cy + r - 1), (cx + r + 3, cy + r + 3)], fill=(255, 255, 255, 220), width=2)
    return image


def _icon_symbol(tile_size: int, palette: str, seed: int) -> Image.Image:
    """Black-rose / occult wall marking used for investigation clues."""
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cx = cy = tile_size // 2
    # Thorned circle
    r = tile_size // 3
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=parse_color("#1a1a1a"), width=2)
    draw.ellipse([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2], outline=parse_color("#4a1a2a"), width=1)
    # Rose petals
    petal = parse_color("#2a0a12")
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        px = cx + int(math.cos(rad) * r * 0.45)
        py = cy + int(math.sin(rad) * r * 0.45)
        draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=petal)
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=parse_color("#0a0a0a"))
    # Faint glow
    glow = parse_color("#6a2a3a")[:3] + (60,)
    draw.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], outline=glow, width=1)
    return image


def _icon_altar(tile_size: int, palette: str, seed: int) -> Image.Image:
    theme = get_theme(palette)
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stone = parse_color(theme["wall"][0])
    gold = parse_color(theme["accent"][0])
    m = max(3, tile_size // 8)
    # Base
    draw.rectangle([m + 2, tile_size // 2, tile_size - m - 2, tile_size - m], fill=stone, outline=shade(stone, -0.3))
    # Top slab
    draw.rectangle([m, tile_size // 3, tile_size - m, tile_size // 2 + 2], fill=shade(stone, 0.15), outline=gold)
    # Cloth
    draw.rectangle([m + 4, tile_size // 3 + 2, tile_size - m - 4, tile_size // 2], fill=parse_color("#6a1a2a"))
    return image


def _icon_candle(tile_size: int, palette: str, seed: int) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cx = tile_size // 2
    wax = parse_color("#f0e6c8")
    flame = parse_color("#ffaa33")
    wick = parse_color("#2a2a2a")
    w = max(3, tile_size // 8)
    top = tile_size // 3
    bottom = tile_size - max(4, tile_size // 6)
    draw.rectangle([cx - w, top, cx + w, bottom], fill=wax, outline=shade(wax, -0.2))
    draw.line([(cx, top - 2), (cx, top + 2)], fill=wick, width=1)
    draw.ellipse([cx - 3, top - 8, cx + 3, top - 1], fill=flame)
    draw.ellipse([cx - 1, top - 7, cx + 1, top - 3], fill=parse_color("#fff5c0"))
    return image


def _icon_tree(tile_size: int, palette: str, seed: int) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    trunk = parse_color("#5a3a1e")
    leaves = parse_color("#2f7a34")
    dark = shade(leaves, -0.25)
    cx = tile_size // 2
    trunk_w = max(3, tile_size // 8)
    trunk_top = tile_size // 2
    trunk_bottom = tile_size - max(4, tile_size // 6)
    draw.rectangle([cx - trunk_w, trunk_top, cx + trunk_w, trunk_bottom], fill=trunk)
    crown_r = tile_size // 3
    draw.ellipse([cx - crown_r, max(2, tile_size // 8), cx + crown_r, trunk_top + crown_r // 2], fill=leaves, outline=dark)
    draw.ellipse([cx - crown_r + 4, max(4, tile_size // 6), cx - crown_r + 8, trunk_top + 2], fill=shade(leaves, 0.12))
    return image


def _icon_briar(tile_size: int, palette: str, seed: int) -> Image.Image:
    rng = random.Random(seed)
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    leaf = parse_color("#2d5f28")
    thorn = parse_color("#6d4a2a")
    for _ in range(5):
        x = rng.randint(tile_size // 5, tile_size * 4 // 5)
        y = rng.randint(tile_size // 5, tile_size * 4 // 5)
        r = rng.randint(tile_size // 10, tile_size // 6)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=leaf, outline=shade(leaf, -0.2))
        draw.line([(x, y - r), (x, y - r - 3)], fill=thorn, width=2)
    return image


def _icon_switch(tile_size: int, palette: str, seed: int) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    plate = parse_color("#6a6a6a")
    lever = parse_color("#d4af37")
    m = max(4, tile_size // 6)
    draw.rounded_rectangle([m, m + 4, tile_size - m, tile_size - m], radius=3, fill=plate, outline=shade(plate, -0.25))
    base_x = tile_size // 2
    base_y = tile_size - m - 2
    draw.rectangle([base_x - 3, base_y - 2, base_x + 3, base_y + 2], fill=shade(lever, -0.2))
    draw.line([(base_x, base_y - 2), (base_x + tile_size // 5, m + 6)], fill=lever, width=3)
    draw.ellipse([base_x + tile_size // 5 - 3, m + 4, base_x + tile_size // 5 + 3, m + 10], fill=lever)
    return image


def _icon_difficult_terrain(tile_size: int, palette: str, seed: int) -> Image.Image:
    rng = random.Random(seed)
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    base = parse_color("#7a6a4f")
    rock = parse_color("#5a5040")
    draw.rectangle([0, 0, tile_size - 1, tile_size - 1], fill=base)
    for _ in range(8):
        x = rng.randint(2, tile_size - 6)
        y = rng.randint(2, tile_size - 6)
        r = rng.randint(2, max(3, tile_size // 10))
        draw.ellipse([x, y, x + r, y + r], fill=rock)
    return image


def _icon_chasm(tile_size: int, palette: str, seed: int) -> Image.Image:
    image = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    edge = parse_color("#4a3a2a")
    void = parse_color("#120808")
    glow = parse_color("#8a2020")
    m = max(3, tile_size // 8)
    draw.ellipse([m, m, tile_size - m, tile_size - m], fill=void, outline=edge, width=2)
    draw.ellipse([m + 4, m + 4, tile_size - m - 4, tile_size - m - 4], outline=glow, width=1)
    return image


def wall_neighbor_mask(grid, x: int, y: int, wall_chars: set[str]) -> int:
    mask = 0
    if y > 0 and grid[x][y - 1] in wall_chars:
        mask |= 1
    if x < len(grid) - 1 and grid[x + 1][y] in wall_chars:
        mask |= 2
    if y < len(grid[0]) - 1 and grid[x][y + 1] in wall_chars:
        mask |= 4
    if x > 0 and grid[x - 1][y] in wall_chars:
        mask |= 8
    return mask


def apply_atmosphere(
    image: Image.Image,
    *,
    palette: str,
    illumination: float = 0.7,
    fog_strength: float = 0.0,
) -> Image.Image:
    """Darken / tint the finished map to match theme and lighting."""
    theme = get_theme(palette)
    result = image.convert("RGBA")
    # Illumination overlay
    darkness = max(0.0, min(0.75, 1.0 - illumination))
    if darkness > 0.02:
        overlay = Image.new("RGBA", result.size, (0, 0, 20, int(180 * darkness)))
        result = Image.alpha_composite(result, overlay)
    if fog_strength > 0.02:
        fog_color = parse_color(theme["fog"][0])
        fog = Image.new("RGBA", result.size, fog_color[:3] + (int(120 * fog_strength),))
        result = Image.alpha_composite(result, fog)
        result = result.filter(ImageFilter.SMOOTH)
    return result
