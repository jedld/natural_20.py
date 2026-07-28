"""Compose tile-based map images from MapGrid data."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from natural20.map_image.assets import load_token_image, resolve_asset_path
from natural20.map_image.diffusion import build_map_prompt, generate_background
from natural20.map_image.grid import MapGrid, load_map_grid, load_map_grid_from_campaign
from natural20.map_image.tiles import (
    apply_atmosphere,
    door_tile,
    floor_tile,
    marker_tile,
    object_icon,
    parse_color,
    theme_for_name,
    wall_neighbor_mask,
    wall_tile,
    water_tile,
)
from natural20.yaml_loader import load_campaign_yaml, templates_root

WALL_CHARS = {"#"}
FLOOR_CHARS = {".", None}
VOID_CHAR = "_"
DOOR_CHARS = {"-", "|"}

DEFAULT_OBJECT_COLORS = {
    "chest": "#8b5a2b",
    "wooden_door": "#6b4423",
    "door": "#6b4423",
    "teleporter": "#3a5fb3",
    "pit_trap": "#2a2a2a",
    "campfire": "#c94a1a",
    "barrel": "#6b4f2d",
    "water": "#2a4f6a",
    "ground": "#6f675c",
    "stone_wall": "#2f2f35",
    "note": "#d4c47a",
    "interactive_object": "#c9b23a",
    "altar": "#8a7a6a",
    "candle": "#f0e6c8",
    "npc": "#3a8f4a",
}


@dataclass
class RenderConfig:
    tile_size: int = 64
    palette: str = "stone"
    layers: tuple[str, ...] = ("base", "objects", "entities", "meta")
    show_grid: bool = False
    grid_color: str = "#00000055"
    background_opacity: float = 1.0
    diffusion_provider: str | None = None
    diffusion_style: str = "fantasy battlemap"
    diffusion_quality: str = "medium"
    mcp_url: str | None = None
    campaign_root: Path | None = None
    object_catalog: dict[str, Any] = field(default_factory=dict)
    illumination: float = 0.7
    fog_strength: float = 0.0
    atmosphere: bool = True
    skip_background_image: bool = False
    use_gen_textures: bool = True


class MapImageRenderer:
    def __init__(self, grid: MapGrid, config: RenderConfig | None = None):
        self.grid = grid
        self.config = config or RenderConfig()
        self._wall_chars = set(WALL_CHARS)
        self._register_wall_legend_types()
        self.palette = self._resolve_palette()

    def _resolve_palette(self) -> str:
        if self.grid.render_hints.get("palette"):
            return str(self.grid.render_hints["palette"])
        if self.config.palette and self.config.palette != "stone":
            return self.config.palette
        inferred = theme_for_name(
            self.grid.name,
            self.grid.description,
            map_id="",
        )
        if self.config.palette == "stone" and inferred != "stone":
            return inferred
        return self.config.palette or inferred

    def _register_wall_legend_types(self) -> None:
        for token, entry in self.grid.legend.items():
            if not isinstance(entry, dict):
                continue
            obj_type = str(entry.get("type", "")).lower()
            if obj_type in {"stone_wall", "barrier", "wall"}:
                self._wall_chars.add(str(token))

    def render(self) -> Image.Image:
        width_px = self.grid.width * self.config.tile_size
        height_px = self.grid.height * self.config.tile_size
        canvas = Image.new("RGBA", (width_px, height_px), parse_color("#0d0d10"))

        background = None
        if not self.config.skip_background_image:
            background = self._load_background_image(width_px, height_px)
        if background is not None:
            opacity = max(0.0, min(1.0, self.config.background_opacity))
            if opacity < 1.0:
                alpha = background.split()[3]
                alpha = alpha.point(lambda p: int(p * opacity))
                background.putalpha(alpha)
            canvas.alpha_composite(background)

        if self.config.diffusion_provider:
            diffusion_bg = self._render_diffusion_background(width_px, height_px)
            if diffusion_bg is not None:
                opacity = max(0.0, min(1.0, self.config.background_opacity))
                if opacity < 1.0:
                    alpha = diffusion_bg.split()[3]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    diffusion_bg.putalpha(alpha)
                canvas = Image.alpha_composite(diffusion_bg, canvas)

        if "base" in self.config.layers:
            self._render_base_layer(canvas)
        if "objects" in self.config.layers:
            self._render_token_layer(canvas, "base_1")
            self._render_token_layer(canvas, "base_2")
        if "meta" in self.config.layers:
            self._render_token_layer(canvas, "meta")
        if "entities" in self.config.layers:
            self._render_entities(canvas)

        if self.config.atmosphere:
            canvas = apply_atmosphere(
                canvas,
                palette=self.palette,
                illumination=self.config.illumination,
                fog_strength=self.config.fog_strength,
            )

        if self.config.show_grid:
            self._draw_grid(canvas)
        return canvas

    def _load_background_image(self, width_px: int, height_px: int) -> Image.Image | None:
        if not self.grid.background_image:
            return None
        path = resolve_asset_path(
            self.grid.background_image,
            campaign_root=self.config.campaign_root,
            subdir="maps",
        )
        if path is None:
            return None
        image = Image.open(path).convert("RGBA")
        offset_x, offset_y = 0, 0
        if self.grid.image_offset_px:
            offset_x = int(self.grid.image_offset_px[0])
            offset_y = int(self.grid.image_offset_px[1])
        layer = Image.new("RGBA", (width_px, height_px), (0, 0, 0, 0))
        layer.paste(image, (offset_x, offset_y))
        if layer.size != (width_px, height_px):
            layer = layer.resize((width_px, height_px), Image.Resampling.LANCZOS)
        return layer

    def _render_diffusion_background(self, width_px: int, height_px: int) -> Image.Image | None:
        prompt = build_map_prompt(
            self.grid.name,
            self.grid.description,
            style=self.config.diffusion_style,
            palette=self.palette,
        )
        generated = generate_background(
            prompt,
            width_px,
            height_px,
            provider=self.config.diffusion_provider or "openai",
            mcp_url=self.config.mcp_url,
            quality=self.config.diffusion_quality,
        )
        if generated is None:
            return None
        base = Image.new("RGBA", (width_px, height_px), parse_color("#0d0d10"))
        base.alpha_composite(generated)
        return base

    def _render_base_layer(self, canvas: Image.Image) -> None:
        for x in range(self.grid.width):
            for y in range(self.grid.height):
                char = self.grid.cell("base", x, y)
                tile = self._terrain_tile(char, x, y)
                if tile is not None:
                    self._paste_tile(canvas, tile, x, y)

    def _terrain_tile(self, char: str | None, x: int, y: int) -> Image.Image | None:
        palette = self.palette
        if char == VOID_CHAR:
            return None
        if char in WALL_CHARS:
            mask = wall_neighbor_mask(self.grid.base, x, y, self._wall_chars)
            return wall_tile(self.config.tile_size, mask, palette)
        if char in DOOR_CHARS:
            orientation = "horizontal" if char == "-" else "vertical"
            return door_tile(self.config.tile_size, orientation, palette)
        if char in FLOOR_CHARS or char is None:
            return floor_tile(self.config.tile_size, palette, x * 997 + y)

        legend = self.grid.legend.get(char or "")
        if isinstance(legend, dict):
            obj_type = str(legend.get("type", "")).lower()
            if obj_type == "water":
                return water_tile(self.config.tile_size, x * 31 + y, palette)
            if obj_type in {"stone_wall", "barrier", "wall"}:
                mask = wall_neighbor_mask(self.grid.base, x, y, self._wall_chars | {char})
                return wall_tile(self.config.tile_size, mask, palette)
            if obj_type == "ground":
                return floor_tile(self.config.tile_size, palette, x * 997 + y)
            # Legend token on base layer: floor under a thematic object
            icon = object_icon(self.config.tile_size, obj_type, palette, x * 31 + y)
            if icon is not None:
                floor = floor_tile(self.config.tile_size, palette, x * 997 + y)
                composed = floor.copy()
                composed.alpha_composite(icon)
                return composed

        return floor_tile(self.config.tile_size, palette, x * 997 + y)

    def _render_token_layer(self, canvas: Image.Image, layer_name: str) -> None:
        for x in range(self.grid.width):
            for y in range(self.grid.height):
                char = self.grid.cell(layer_name, x, y)
                if not char or char == ".":
                    continue
                tile = self._object_tile(char, x, y)
                if tile is not None:
                    self._paste_tile(canvas, tile, x, y)

    def _object_tile(
        self,
        token: str,
        x: int,
        y: int,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> Image.Image | None:
        if token in DOOR_CHARS or token in WALL_CHARS:
            return None

        legend = self.grid.legend.get(token, {})
        if not isinstance(legend, dict):
            legend = {}
        if overrides:
            legend = {**legend, **overrides}

        obj_type = str(legend.get("type", "")).lower()
        if obj_type == "mask":
            return None
        if obj_type == "npc":
            return self._npc_marker(legend, token)

        sprite = self._sprite_for_type(obj_type, legend)
        if sprite is not None:
            return sprite

        # Prefer name/label hints before generic type icons
        name = str(legend.get("name") or legend.get("label") or token).lower()
        for hint in ("altar", "candle", "note", "teleporter", "chest", "barrel", "campfire", "symbol", "rose", "pit"):
            if hint in name:
                icon_kind = "symbol" if hint in {"symbol", "rose"} else ("pit_trap" if hint == "pit" else hint)
                icon = object_icon(self.config.tile_size, icon_kind, self.palette, x * 31 + y)
                if icon is not None:
                    return icon

        icon = object_icon(
            self.config.tile_size,
            obj_type or token,
            self.palette,
            x * 31 + y,
        )
        if icon is not None:
            return icon

        color = self._lookup_color(obj_type, legend, fallback="#c9b23a")
        label = str(legend.get("name") or obj_type or token)
        return marker_tile(self.config.tile_size, color, label)

    def _npc_marker(self, legend: dict[str, Any], token: str) -> Image.Image:
        label = legend.get("name", token)
        if label == "_auto_":
            label = str(legend.get("sub_type", token))
        color = self._lookup_color("npc", legend, fallback="#3a8f4a")
        group = str(legend.get("group", "")).lower()
        if group in {"b", "c", "hostile"}:
            color = legend.get("color") or "#b33a3a"
        return marker_tile(self.config.tile_size, str(color), str(label))

    def _sprite_for_type(self, obj_type: str, legend: dict[str, Any]) -> Image.Image | None:
        catalog_entry = self.config.object_catalog.get(obj_type) or {}
        if legend.get("hide_map_token") or catalog_entry.get("hide_map_token"):
            return None
        token_image = legend.get("token_image") or catalog_entry.get("token_image")
        if token_image:
            return load_token_image(
                str(token_image),
                campaign_root=self.config.campaign_root,
                tile_size=self.config.tile_size,
            )
        defaults = {
            "chest": "objects/wood_chest_closed.png",
            "wooden_door": "objects/wooden_door.png",
            "door": "objects/wooden_door.png",
            "pit_trap": "objects/spike_pit.png",
            "campfire": "objects/fireplace.png",
            "fireplace": "objects/fireplace.png",
            "barrel": "objects/barrel.png",
        }
        default_image = defaults.get(obj_type)
        if default_image:
            sprite = load_token_image(
                default_image,
                campaign_root=self.config.campaign_root,
                tile_size=self.config.tile_size,
            )
            if sprite is not None:
                return sprite
        return None

    def _lookup_color(self, obj_type: str, legend: dict[str, Any], *, fallback: str) -> str:
        catalog_entry = self.config.object_catalog.get(obj_type) or {}
        for source in (legend, catalog_entry):
            color = source.get("color")
            if color:
                return str(color)
        return DEFAULT_OBJECT_COLORS.get(obj_type, fallback)

    def _render_entities(self, canvas: Image.Image) -> None:
        for entry in self.grid.entities:
            pos = entry.get("pos")
            if not pos or len(pos) < 2:
                continue
            x, y = int(pos[0]), int(pos[1])
            token = str(entry.get("token", "?"))
            legend = self.grid.legend.get(token, {})
            if not isinstance(legend, dict):
                legend = {}
            merged = {**legend, **{k: v for k, v in entry.items() if k not in {"pos", "token"}}}
            overrides = entry.get("overrides") or {}
            if isinstance(overrides, dict):
                merged = {**merged, **overrides}

            obj_type = str(merged.get("type", "")).lower()
            if obj_type == "npc" or merged.get("sub_type"):
                tile = self._npc_marker(merged, token)
            else:
                tile = self._object_tile(token, x, y, overrides=merged)
                if tile is None:
                    color = self._lookup_color(obj_type or "interactive_object", merged, fallback="#3a5fb3")
                    tile = marker_tile(
                        self.config.tile_size,
                        color,
                        str(merged.get("label") or merged.get("name") or token),
                    )
            self._paste_tile(canvas, tile, x, y)

    def _paste_tile(self, canvas: Image.Image, tile: Image.Image, x: int, y: int) -> None:
        px = x * self.config.tile_size
        py = y * self.config.tile_size
        if tile.size != (self.config.tile_size, self.config.tile_size):
            tile = tile.resize((self.config.tile_size, self.config.tile_size), Image.Resampling.LANCZOS)
        canvas.alpha_composite(tile.convert("RGBA"), (px, py))

    def _draw_grid(self, canvas: Image.Image) -> None:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(canvas)
        color = parse_color(self.config.grid_color)
        step = self.config.tile_size
        width_px, height_px = canvas.size
        for x in range(0, width_px + 1, step):
            draw.line([(x, 0), (x, height_px)], fill=color, width=1)
        for y in range(0, height_px + 1, step):
            draw.line([(0, y), (width_px, y)], fill=color, width=1)


def _load_object_catalog(campaign_root: Path | None) -> dict[str, Any]:
    catalog: dict[str, Any] = {}
    roots = []
    if campaign_root is not None:
        roots.append(campaign_root)
    roots.append(templates_root())
    try:
        for root in roots:
            try:
                objects = load_campaign_yaml(root, "items", "objects")
            except FileNotFoundError:
                continue
            if isinstance(objects, dict):
                catalog.update(objects)
    except Exception:
        pass
    return catalog


def _illumination_from_properties(properties: dict[str, Any] | None) -> float:
    if not properties:
        return 0.7
    map_block = properties.get("map") or {}
    value = map_block.get("illumination")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.7


def _fog_from_properties(properties: dict[str, Any] | None) -> float:
    if not properties:
        return 0.0
    effect = properties.get("default_effect") or {}
    if str(effect.get("effect", "")).lower() != "fog":
        return 0.0
    config = effect.get("config") or {}
    opacity = config.get("opacity", 0.4)
    try:
        return max(0.0, min(1.0, float(opacity) * 0.6))
    except (TypeError, ValueError):
        return 0.25


def render_map_image(
    *,
    output: str | Path,
    campaign: str | Path | None = None,
    map_name: str | None = None,
    input_yaml: str | Path | None = None,
    tile_size: int = 64,
    palette: str | None = None,
    layers: Iterable[str] | None = None,
    show_grid: bool = False,
    image_format: str = "png",
    diffusion: str | None = None,
    diffusion_style: str = "fantasy battlemap",
    diffusion_quality: str = "medium",
    mcp_url: str | None = None,
    background_opacity: float = 1.0,
    atmosphere: bool = True,
    skip_background_image: bool = False,
) -> Path:
    from natural20.yaml_loader import load_yaml

    campaign_root = Path(campaign).resolve() if campaign else None
    properties: dict[str, Any] | None = None
    if input_yaml:
        properties = load_yaml(input_yaml, campaign_root=campaign_root)
        grid = load_map_grid(input_yaml, campaign_root=campaign_root)
    elif campaign_root and map_name:
        grid = load_map_grid_from_campaign(campaign_root, map_name)
        # Reload properties for illumination/fog
        from natural20.map_image.grid import load_map_grid_from_campaign as _
        candidates = [
            campaign_root / map_name,
            campaign_root / "maps" / Path(map_name).name,
        ]
        for candidate in candidates:
            path = candidate if str(candidate).endswith(".yml") else Path(str(candidate) + ".yml")
            if path.is_file():
                props = load_yaml(path, campaign_root=campaign_root)
                if isinstance(props, dict):
                    properties = props
                break
    else:
        raise ValueError("Provide --input or both --campaign and --map")

    hints = grid.render_hints or {}
    if hints.get("tile_size"):
        tile_size = int(hints["tile_size"])

    resolved_palette = palette
    if hints.get("palette"):
        resolved_palette = str(hints["palette"])
    if not resolved_palette:
        resolved_palette = theme_for_name(grid.name, grid.description, map_id=map_name or "")

    config = RenderConfig(
        tile_size=tile_size,
        palette=resolved_palette,
        layers=tuple(layers or ("base", "objects", "entities", "meta")),
        show_grid=show_grid,
        diffusion_provider=diffusion,
        diffusion_style=diffusion_style,
        diffusion_quality=diffusion_quality,
        mcp_url=mcp_url,
        background_opacity=background_opacity,
        campaign_root=campaign_root,
        object_catalog=_load_object_catalog(campaign_root),
        illumination=_illumination_from_properties(properties),
        fog_strength=_fog_from_properties(properties),
        atmosphere=atmosphere,
        skip_background_image=skip_background_image,
    )
    renderer = MapImageRenderer(grid, config)
    image = renderer.render()

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = image_format.lower()
    if fmt in {"jpg", "jpeg"}:
        image.convert("RGB").save(output_path, format="JPEG", quality=92)
    else:
        image.save(output_path, format="PNG")
    return output_path.resolve()
