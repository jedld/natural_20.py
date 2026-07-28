"""Compose spell scroll item icons from a parchment background + spell icon."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCROLL_BACKGROUND = _REPO_ROOT / "scripts" / "image_generators" / "spell_scroll.png"
DEFAULT_SPELL_SCROLL_SCALE = 2.5


def spell_scroll_spell_slug(meta: dict[str, Any]) -> str | None:
    spell = str(meta.get("spell") or "").strip()
    return spell or None


def is_spell_scroll_item(meta: dict[str, Any]) -> bool:
    item_type = str(meta.get("type") or "").replace("_", " ").lower()
    if item_type != "scroll":
        return False
    return spell_scroll_spell_slug(meta) is not None


def overlay_spell_on_scroll(
    background_path: Path | str,
    spell_icon_path: Path | str,
    *,
    scale_factor: float = DEFAULT_SPELL_SCROLL_SCALE,
    position: tuple[int, int] | None = None,
) -> Image.Image:
    background = Image.open(background_path)
    target = Image.open(spell_icon_path)
    if target.mode != "RGBA":
        target = target.convert("RGBA")

    if scale_factor != 1.0:
        new_width = int(target.width * scale_factor)
        new_height = int(target.height * scale_factor)
        target = target.resize((new_width, new_height), Image.Resampling.LANCZOS)

    result = background.convert("RGBA") if background.mode != "RGBA" else background.copy()
    if position is None:
        x = (result.width - target.width) // 2
        y = (result.height - target.height) // 2
    else:
        x, y = position

    composite = Image.new("RGBA", result.size, (0, 0, 0, 0))
    composite.paste(target, (x, y))
    merged = Image.alpha_composite(result, composite)
    return merged.convert("RGB")


def render_spell_scroll_icon(
    *,
    spell_slug: str,
    spell_icon_path: Path,
    background_path: Path | None = None,
    scale_factor: float = DEFAULT_SPELL_SCROLL_SCALE,
    position: tuple[int, int] | None = None,
) -> Image.Image:
    background = background_path or DEFAULT_SCROLL_BACKGROUND
    if not background.is_file():
        raise FileNotFoundError(f"Spell scroll background not found: {background}")
    if not spell_icon_path.is_file():
        raise FileNotFoundError(f"Spell icon not found: {spell_icon_path}")
    return overlay_spell_on_scroll(
        background,
        spell_icon_path,
        scale_factor=scale_factor,
        position=position,
    )
