"""MCP-generated theme texture packs for map tile rendering."""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Callable

from PIL import Image

from natural20.image_gen.mcp_client import ImageGenMcpClient, default_mcp_url

# Surfaces we cache per theme palette.
TEXTURE_SURFACES = ("floor", "wall", "water")

NEGATIVE = (
    "text, watermark, logo, UI, map grid, characters, creatures, furniture, "
    "perspective view, isometric buildings, readable letters, collage"
)

THEME_TEXTURE_PROMPTS: dict[str, dict[str, str]] = {
    "cathedral": {
        "floor": (
            "Seamless top-down texture of polished cathedral flagstones, cool violet-grey marble, "
            "thin gold inlay seams, sacred gothic floor, soft candle light, no objects, tileable."
        ),
        "wall": (
            "Seamless top-down gothic cathedral wall texture, carved purple-grey stone blocks, "
            "arching mortar lines, stained-glass color flecks, solemn, tileable."
        ),
        "water": (
            "Seamless top-down holy water basin texture, deep indigo with gold sparkle reflections, tileable."
        ),
    },
    "sewer": {
        "floor": (
            "Seamless top-down filthy sewer walkway texture, wet green-black bricks, algae slime, "
            "moss, dirty moisture sheen, tileable, no people."
        ),
        "wall": (
            "Seamless top-down sewer tunnel wall texture, slimy dark teal bricks, mold stains, "
            "rust streaks, tileable."
        ),
        "water": (
            "Seamless top-down stagnant sewer channel water, murky olive-green with scum, tileable."
        ),
    },
    "prison": {
        "floor": (
            "Seamless top-down prison cell floor texture, cold iron-grey stone slabs, "
            "scratches, dried dirt, oppressive, tileable."
        ),
        "wall": (
            "Seamless top-down prison wall texture, dark iron bars suggestion in stone, "
            "cold blue-grey blocks, damp, tileable."
        ),
        "water": (
            "Seamless top-down puddle of dirty prison water, steel-blue grey, tileable."
        ),
    },
    "manor": {
        "floor": (
            "Seamless top-down wealthy manor parquet wood floor, warm walnut and amber planks, "
            "rich varnish, candlelit noir, tileable."
        ),
        "wall": (
            "Seamless top-down manor interior wall texture, dark wood paneling with burgundy "
            "wallpaper hint, ornate, tileable."
        ),
        "water": (
            "Seamless top-down decorative fountain water, deep teal with warm reflections, tileable."
        ),
    },
    "street": {
        "floor": (
            "Seamless top-down rainy cobblestone street texture, wet dark basalt stones, "
            "gaslight orange reflections in puddles, urban noir, tileable."
        ),
        "wall": (
            "Seamless top-down city building facade texture from above, soot-stained brick and "
            "stone, gaslamp amber accents, tileable."
        ),
        "water": (
            "Seamless top-down street puddle water, black-blue with orange lamp reflections, tileable."
        ),
    },
    "cobble": {
        "floor": (
            "Seamless top-down market cobblestones, warm grey oval stones, dusty mortar, tileable."
        ),
        "wall": (
            "Seamless top-down market stall wall / brick texture, sandy tan bricks, tileable."
        ),
        "water": (
            "Seamless top-down shallow fountain water, blue-grey, tileable."
        ),
    },
    "tavern": {
        "floor": (
            "Seamless top-down tavern floorboards, scuffed honey-oak planks with spilled ale stains, "
            "warm firelight, tileable."
        ),
        "wall": (
            "Seamless top-down tavern wall texture, dark timber beams and plaster, warm brown, tileable."
        ),
        "water": (
            "Seamless top-down spilled drink puddle, amber-brown liquid sheen, tileable."
        ),
    },
    "docks": {
        "floor": (
            "Seamless top-down wet dock planks, grey-blue weathered wood, salt stains, "
            "rope fibers, river mist, tileable."
        ),
        "wall": (
            "Seamless top-down warehouse / pier wall texture, barnacle-stained timber and stone, tileable."
        ),
        "water": (
            "Seamless top-down dark river water beside docks, oily blue-black ripples, tileable."
        ),
    },
    "dirt": {
        "floor": (
            "Seamless top-down packed cave dirt floor, brown earth with gravel, tileable."
        ),
        "wall": (
            "Seamless top-down cave rock wall texture, rough brown stone, tileable."
        ),
        "water": (
            "Seamless top-down muddy cave pool, brown-green water, tileable."
        ),
    },
    "grass": {
        "floor": (
            "Seamless top-down meadow grass texture, varied greens, soft dirt patches, tileable."
        ),
        "wall": (
            "Seamless top-down garden stone wall texture, mossy pale stones, tileable."
        ),
        "water": (
            "Seamless top-down clear pond water, blue-green, tileable."
        ),
    },
    "stone": {
        "floor": (
            "Seamless top-down dungeon stone floor, cool grey flagstones, tileable."
        ),
        "wall": (
            "Seamless top-down dungeon stone wall bricks, grey mortar, tileable."
        ),
        "water": (
            "Seamless top-down underground pool water, deep blue, tileable."
        ),
    },
}


def default_texture_root() -> Path:
    env = os.getenv("N20_MAP_TEXTURE_ROOT")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "natural20" / "map_textures"


def texture_path(theme: str, surface: str, root: Path | None = None) -> Path:
    root = root or default_texture_root()
    return root / theme / f"{surface}.png"


def sample_texture(atlas: Image.Image, tile_size: int, seed: int) -> Image.Image:
    """Crop a seeded square from a texture atlas and resize to tile_size."""
    atlas = atlas.convert("RGBA")
    w, h = atlas.size
    side = min(w, h)
    if side < 8:
        return atlas.resize((tile_size, tile_size), Image.Resampling.LANCZOS)
    max_origin = max(0, side - min(side, max(tile_size * 2, 64)))
    rng_x = seed % (max_origin + 1)
    rng_y = (seed // 7) % (max_origin + 1)
    crop_side = min(side, max(tile_size * 2, 64))
    x0 = min(rng_x, w - crop_side)
    y0 = min(rng_y, h - crop_side)
    patch = atlas.crop((x0, y0, x0 + crop_side, y0 + crop_side))
    return patch.resize((tile_size, tile_size), Image.Resampling.LANCZOS)


@lru_cache(maxsize=64)
def load_texture(theme: str, surface: str, root: str | None = None) -> Image.Image | None:
    path = texture_path(theme, surface, Path(root) if root else None)
    if not path.is_file():
        return None
    return Image.open(path).convert("RGBA")


def clear_texture_cache() -> None:
    load_texture.cache_clear()
    try:
        from natural20.map_image.tiles import floor_tile, wall_tile, water_tile

        floor_tile.cache_clear()
        wall_tile.cache_clear()
        water_tile.cache_clear()
    except Exception:
        pass


def ensure_theme_textures(
    themes: list[str],
    *,
    root: Path | None = None,
    mcp_url: str | None = None,
    force: bool = False,
    quality: str = "medium",
    generator: Callable[..., object] | None = None,
) -> list[Path]:
    """Generate missing floor/wall/water atlases for each theme via Image Gen MCP."""
    root = root or default_texture_root()
    written: list[Path] = []
    client = None
    owns = False
    try:
        for theme in themes:
            prompts = THEME_TEXTURE_PROMPTS.get(theme) or THEME_TEXTURE_PROMPTS["stone"]
            for surface in TEXTURE_SURFACES:
                out = texture_path(theme, surface, root)
                if out.is_file() and not force:
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                prompt = prompts.get(surface) or THEME_TEXTURE_PROMPTS["stone"][surface]
                if generator is None:
                    if client is None:
                        client = ImageGenMcpClient(mcp_url or default_mcp_url())
                        client.initialize()
                        owns = True
                    result = client.generate_image(
                        prompt=prompt,
                        size="1024x1024",
                        quality=quality,
                        negative_prompt=NEGATIVE,
                        output_format="png",
                    )
                    image = result.image
                else:
                    result = generator(prompt=prompt, size="1024x1024", quality=quality)
                    image = result.image if hasattr(result, "image") else result
                image.convert("RGBA").save(out, format="PNG")
                written.append(out)
                clear_texture_cache()
    finally:
        if owns and client is not None:
            client.close()
    return written


def themes_needed_for_campaign(campaign: Path) -> list[str]:
    from natural20.map_image.grid import load_map_grid_from_campaign
    from natural20.map_image.tiles import theme_for_name

    themes: set[str] = set()
    maps_dir = Path(campaign) / "maps"
    if maps_dir.is_dir():
        for path in maps_dir.glob("*.yml"):
            if path.name == "monsters.yml":
                continue
            try:
                grid = load_map_grid_from_campaign(campaign, path.stem)
            except Exception:
                continue
            hint = (grid.render_hints or {}).get("palette")
            if hint:
                themes.add(str(hint))
            else:
                themes.add(theme_for_name(grid.name, grid.description, path.stem))
    if not themes:
        themes.update(THEME_TEXTURE_PROMPTS.keys())
    return sorted(themes)
