"""Generate object spawner editor icons from objects.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from natural20.map_image.tiles import object_icon
from natural20.image_gen.editor_asset_paths import (
    campaigns_defining_object,
    default_editor_output_dir,
    editor_output_dir_for_object,
    object_editor_scope,
    templates_editor_dir,
)
from webapp.blueprints.helpers.object_spawner_utils import (
    build_available_object_entry,
    resolve_spawner_category,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EDITOR_OUTPUT = templates_editor_dir()

_SKIP_CATEGORIES = frozenset({"walls", "door_walls"})
_SKIP_ITEM_CLASSES = frozenset({
    "StoneWall",
    "StoneWallDirectional",
    "DoorObjectWall",
})

_ITEM_CLASS_ICON_KIND: dict[str, str] = {
    "Switch": "switch",
    "Chasm": "chasm",
    "ProximityTrigger": "campfire",
    "PitTrap": "pit_trap",
    "Teleporter": "teleporter",
    "Chest": "chest",
    "DoorObject": "wooden_door",
}


def editor_floor_tile(size: int = 64) -> Image.Image:
    """Stone floor background matching generate_wall_door_tile.py."""
    img = Image.new("RGB", (size, size), color="#8B7355")
    draw = ImageDraw.Draw(img)
    for i in range(0, size, 8):
        for j in range(0, size, 8):
            if i > 0:
                draw.line([(i, 0), (i, size)], fill="#7A6B4F", width=1)
            if j > 0:
                draw.line([(0, j), (size, j)], fill="#7A6B4F", width=1)
    return img


def resolve_editor_icon_kind(object_id: str, object_data: dict[str, Any]) -> str:
    token_image = str(object_data.get("token_image") or "").strip()
    if token_image:
        return token_image.replace(".png", "")

    item_class = str(object_data.get("item_class") or "").strip()
    if item_class in _ITEM_CLASS_ICON_KIND:
        return _ITEM_CLASS_ICON_KIND[item_class]

    return object_id


def should_generate_editor_icon(object_id: str, object_data: dict[str, Any]) -> bool:
    if object_data.get("placeable") is False:
        return False
    item_class = str(object_data.get("item_class") or "").strip()
    if item_class in _SKIP_ITEM_CLASSES:
        return False
    category = resolve_spawner_category(object_id, object_data)
    if category in _SKIP_CATEGORIES:
        return False
    return True


def render_object_editor_icon(
    object_id: str,
    object_data: dict[str, Any],
    *,
    size: int = 64,
    palette: str = "dirt",
) -> Image.Image | None:
    kind = resolve_editor_icon_kind(object_id, object_data)
    seed = sum(ord(ch) for ch in object_id) % 10_000
    icon = object_icon(size, kind, palette, seed)
    if icon is None:
        icon = object_icon(size, object_id, palette, seed)
    if icon is None:
        return None

    floor = editor_floor_tile(size)
    if icon.mode != "RGBA":
        icon = icon.convert("RGBA")
    scale = min(1.0, (size * 0.82) / max(icon.width, icon.height))
    if scale < 1.0:
        new_size = (max(1, int(icon.width * scale)), max(1, int(icon.height * scale)))
        icon = icon.resize(new_size, Image.Resampling.LANCZOS)
    x = (size - icon.width) // 2
    y = (size - icon.height) // 2
    floor.paste(icon, (x, y), icon)
    return floor


def generate_object_editor_icons(
    objects: dict[str, Any],
    *,
    output_dir: Path | None = None,
    campaign_root: str | Path | None = None,
    size: int = 64,
    palette: str = "dirt",
    force: bool = False,
) -> list[tuple[str, Path, str]]:
    default_dir = output_dir or default_editor_output_dir(campaign_root)
    results: list[tuple[str, Path, str]] = []

    for object_id, object_data in (objects or {}).items():
        if not object_id or not isinstance(object_data, dict):
            continue
        if not should_generate_editor_icon(str(object_id), object_data):
            continue

        entry = build_available_object_entry(str(object_id), object_data)
        if not entry:
            continue

        if output_dir is None:
            scope = object_editor_scope(str(object_id), campaign_root=campaign_root)
            if scope == "campaign" and campaign_root is None:
                roots = campaigns_defining_object(str(object_id))
                if len(roots) != 1:
                    continue
            out_dir = editor_output_dir_for_object(str(object_id), campaign_root=campaign_root)
        else:
            out_dir = output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / entry["image"]
        if output_path.is_file() and not force:
            continue

        rendered = render_object_editor_icon(str(object_id), object_data, size=size, palette=palette)
        if rendered is None:
            results.append((str(object_id), output_path, "skipped: no procedural icon"))
            continue

        rendered.save(output_path, format="PNG")
        results.append((str(object_id), output_path, "written"))

    if results and output_dir is None and campaign_root is None:
        # Ensure default_dir exists even when everything was skipped.
        default_dir.mkdir(parents=True, exist_ok=True)

    return results
