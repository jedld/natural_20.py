"""Discover, audit, and materialize map tile effect icons.

Map tiles render active effects with:

    assets/effect/<str(effect).lower()>.png

This module scans Python ``*Effect`` classes for tile slugs, validates that each
slug maps to a bundled PNG, and can create missing icons from spell art, simple
placeholders, or the Image Gen MCP (via :mod:`natural20.image_gen.game_icons`).
"""

from __future__ import annotations

import importlib
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

_REPO_ROOT = Path(__file__).resolve().parents[2]
_N20_WEBAPP_STATIC = _REPO_ROOT / "n20-webapp" / "webapp" / "static"
_LEGACY_WEBAPP_STATIC = _REPO_ROOT / "webapp" / "static"
_WEBAPP_STATIC = (
    _N20_WEBAPP_STATIC if _N20_WEBAPP_STATIC.is_dir() else _LEGACY_WEBAPP_STATIC
)
_EFFECT_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Copy spell / effect art before falling back to MCP or placeholders.
_EFFECT_FALLBACK_SPELL_SLUGS: dict[str, str] = {
    "light": "light",
    "color_spray": "color_spray",
    "mage_hand": "mage_hand",
    "spiritual_weapon": "spiritual_weapon",
    "find_familiar": "find_familiar",
    "silvery_barbs": "silvery_barbs",
    "chill_touch": "chill_touch",
    "detect_magic": "detect_magic",
    "darkness": "darkness",
    "stinking_cloud": "stinking_cloud",
    "witch_bolt": "witch_bolt",
    "guidance": "guidance",
    "bardic_inspiration": "guidance",
    "absorb_elements": "absorb_elements",
    "divine_smite": "divine_smite",
}

# Slugs still required when class discovery cannot instantiate the effect.
_EXTRA_RUNTIME_EFFECT_SLUGS = frozenset({
    "engulf",
    "life_drain",
    "protection",
    "stench",
    "strength_drain",
})


def webapp_static_root() -> Path:
    return _WEBAPP_STATIC


def default_effect_output_dir() -> Path:
    return webapp_static_root() / "assets" / "effect"


def default_spell_output_dir() -> Path:
    return webapp_static_root() / "spells"


def effect_icon_path(effect_id: str, *, effect_output_dir: Path | None = None) -> Path:
    base = effect_output_dir or default_effect_output_dir()
    return base / f"{effect_id}.png"


def spell_icon_path(spell_id: str, *, spell_output_dir: Path | None = None) -> Path:
    base = spell_output_dir or default_spell_output_dir()
    return base / f"spell_{spell_id}.png"


def effect_icon_exists(effect_id: str, *, effect_output_dir: Path | None = None) -> bool:
    return effect_icon_path(effect_id, effect_output_dir=effect_output_dir).is_file()


@dataclass
class EffectClassInfo:
    """One tile-visible effect class and its resolved icon slug."""

    class_name: str
    module: str
    slug: str
    slug_source: str  # __str__ | id | class_name
    instantiable: bool
    issues: list[str] = field(default_factory=list)

    @property
    def asset_path(self) -> Path:
        return effect_icon_path(self.slug)

    @property
    def asset_exists(self) -> bool:
        return self.asset_path.is_file()


@dataclass
class EffectAssetAudit:
  """Aggregate audit report for CI and developer tooling."""

  effects: list[EffectClassInfo] = field(default_factory=list)

  @property
  def invalid_slugs(self) -> list[EffectClassInfo]:
      return [e for e in self.effects if e.issues]

  @property
  def missing_assets(self) -> list[EffectClassInfo]:
      return [e for e in self.effects if not e.asset_exists and not e.issues]

  @property
  def ok(self) -> bool:
      return not self.invalid_slugs and not self.missing_assets


def is_valid_effect_slug(slug: str) -> bool:
    if not slug or slug.startswith("<"):
        return False
    if any(ch in slug for ch in " ()\t\n"):
        return False
    return bool(_EFFECT_SLUG_RE.match(slug))


def _camel_effect_name_to_slug(name: str) -> str:
    base = name
    if base.endswith("Effect"):
        base = base[: -len("Effect")]
    slug = re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower()
    return slug


def _default_for_annotation(annotation: Any) -> Any:
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, str):
        return ""
    return None


def build_dummy_effect_instance(cls: type) -> Any | None:
    """Best-effort dummy instance so ``str()`` / ``id`` can be read."""
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return None

    args: list[Any] = []
    for name, param in list(sig.parameters.items())[1:]:
        if name in {"source", "entity", "caster", "owner", "ally", "target", "familiar"}:
            args.append(object())
        elif name in {"battle", "battle_map", "map"}:
            args.append(None)
        elif name in {"color", "damage_type"}:
            args.append("white")
        elif name in {"die"}:
            args.append("1d6")
        elif name in {"duration_seconds", "duration", "range_feet", "hit_point_reduction", "dice_count"}:
            args.append(1)
        elif name in {"spell_properties"}:
            args.append({})
        elif name in {"darkness", "mage_hand", "spiritual_weapon"}:
            args.append(object())
        elif param.default is not inspect.Parameter.empty:
            continue
        else:
            default = _default_for_annotation(param.annotation)
            if default is None and param.kind == inspect.Parameter.VAR_POSITIONAL:
                break
            args.append(default)
    try:
        return cls(*args)
    except Exception:
        return None


def resolve_effect_tile_slug(cls: type, instance: Any | None = None) -> tuple[str, str]:
    """Return ``(slug, source)`` for a tile effect class."""
    built = instance if instance is not None else build_dummy_effect_instance(cls)

    if built is not None and cls.__str__ is not object.__str__:
        slug = str(built).strip().lower()
        if is_valid_effect_slug(slug):
            return slug, "__str__"

    if built is not None:
        id_attr = getattr(cls, "id", None)
        if isinstance(id_attr, property):
            try:
                raw_id = built.id
            except Exception:
                raw_id = None
            if isinstance(raw_id, str):
                slug = raw_id.split(":", 1)[0].strip().lower()
                if is_valid_effect_slug(slug):
                    return slug, "id"

    slug = _camel_effect_name_to_slug(cls.__name__)
    return slug, "class_name"


def _module_name_for_path(path: Path) -> str:
    rel = path.relative_to(_REPO_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _iter_effect_classes(package_name: str = "natural20") -> Iterable[tuple[str, type]]:
    """Yield ``(module_name, EffectClass)`` pairs from the engine tree."""
    del package_name
    package_root = _REPO_ROOT / "natural20"
    seen_modules: set[str] = set()
    for path in sorted(package_root.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        if path.name == "setup.py":
            continue
        module_name = _module_name_for_path(path)
        if module_name in seen_modules:
            continue
        seen_modules.add(module_name)
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if not name.endswith("Effect"):
                continue
            if cls.__module__ != module.__name__:
                continue
            yield module.__name__, cls


def scan_effect_classes(
    *,
    effect_output_dir: Path | None = None,
    extra_slugs: Iterable[str] | None = None,
) -> list[EffectClassInfo]:
    """Scan ``natural20`` for ``*Effect`` classes and validate tile icon slugs."""
    del effect_output_dir  # paths resolved per-entry via effect_icon_path
    seen: dict[str, EffectClassInfo] = {}

    for module_name, cls in _iter_effect_classes():
        instance = build_dummy_effect_instance(cls)
        slug, source = resolve_effect_tile_slug(cls, instance)
        issues: list[str] = []
        if not is_valid_effect_slug(slug):
            issues.append(f"invalid tile slug: {slug!r}")

        info = EffectClassInfo(
            class_name=cls.__name__,
            module=module_name,
            slug=slug,
            slug_source=source,
            instantiable=instance is not None,
            issues=issues,
        )
        prev = seen.get(slug)
        if prev is None or (prev.issues and not issues):
            seen[slug] = info

    for slug in sorted(set(extra_slugs or ()) | _EXTRA_RUNTIME_EFFECT_SLUGS):
        if slug in seen:
            continue
        seen[slug] = EffectClassInfo(
            class_name="",
            module="",
            slug=slug,
            slug_source="extra",
            instantiable=False,
        )

    return sorted(seen.values(), key=lambda e: e.slug)


def audit_effect_assets(
    *,
    effect_output_dir: Path | None = None,
    extra_slugs: Iterable[str] | None = None,
) -> EffectAssetAudit:
    out_dir = effect_output_dir or default_effect_output_dir()
    effects = scan_effect_classes(effect_output_dir=out_dir, extra_slugs=extra_slugs)
    for info in effects:
        if not effect_icon_exists(info.slug, effect_output_dir=out_dir):
            if not any("invalid tile slug" in issue for issue in info.issues):
                pass  # missing asset tracked via missing_assets property
    return EffectAssetAudit(effects=effects)


def discover_runtime_effect_refs(
    *,
    effect_output_dir: Path | None = None,
    extra_slugs: Iterable[str] | None = None,
) -> list[Any]:
    """Build effect icon refs from runtime ``*Effect`` classes."""
    from natural20.image_gen.game_icons import IconAssetRef

    out_dir = effect_output_dir or default_effect_output_dir()
    refs: list[IconAssetRef] = []
    for info in scan_effect_classes(effect_output_dir=out_dir, extra_slugs=extra_slugs):
        if info.issues:
            continue
        label = info.slug.replace("_", " ").title()
        refs.append(
            IconAssetRef(
                kind="effect",
                key=info.slug,
                label=label,
                image_name=info.slug,
                output_path=out_dir / f"{info.slug}.png",
                meta={
                    "slug": info.slug,
                    "class_name": info.class_name,
                    "module": info.module,
                    "slug_source": info.slug_source,
                },
                source="runtime_effects",
            )
        )
    return refs


def effect_fallback_source(
    slug: str,
    *,
    spell_output_dir: Path | None = None,
    effect_output_dir: Path | None = None,
) -> Path | None:
    """Return an existing PNG to copy for *slug*, if any."""
    spell_dir = spell_output_dir or default_spell_output_dir()
    effect_dir = effect_output_dir or default_effect_output_dir()

    spell_slug = _EFFECT_FALLBACK_SPELL_SLUGS.get(slug, slug)
    spell_path = spell_icon_path(spell_slug, spell_output_dir=spell_dir)
    if spell_path.is_file():
        return spell_path

    alias = _EFFECT_FALLBACK_SPELL_SLUGS.get(slug)
    if alias and alias != slug:
        alias_path = effect_icon_path(alias, effect_output_dir=effect_dir)
        if alias_path.is_file():
            return alias_path

    return None


def render_placeholder_effect_icon(
    slug: str,
    *,
    size: int = 128,
    label: str | None = None,
) -> Image.Image:
    """Simple flat placeholder when no spell art or MCP is available."""
    palette = {
        "life_drain": ("#4a148c", "#e1bee7"),
        "protection": ("#1b5e20", "#a5d6a7"),
        "stench": ("#33691e", "#c5e1a5"),
        "strength_drain": ("#b71c1c", "#ffcdd2"),
    }
    bg, fg = palette.get(slug, ("#37474f", "#eceff1"))
    text = (label or slug.replace("_", " ")[:4]).upper()

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, size - 8, size - 8), fill=bg)
    draw.ellipse((20, 20, size - 20, size - 20), outline=fg, width=3)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            max(16, size // 5),
        )
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - 2), text, fill=fg, font=font)
    return img


def materialize_effect_icon(
    ref: Any,
    *,
    mode: str = "auto",
    spell_output_dir: Path | None = None,
    effect_output_dir: Path | None = None,
    size: int = 128,
) -> tuple[bool, str]:
    """Create ``ref.output_path`` without MCP when possible.

    Returns ``(success, note)`` where *note* describes the strategy used.
    """
    if ref.kind != "effect":
        return False, "not an effect ref"

    slug = ref.key
    out = ref.output_path
    if out.is_file():
        return True, "exists"

    effect_output_dir = effect_output_dir or out.parent
    spell_output_dir = spell_output_dir or default_spell_output_dir()

    if mode in {"auto", "copy"}:
        source = effect_fallback_source(
            slug,
            spell_output_dir=spell_output_dir,
            effect_output_dir=effect_output_dir,
        )
        if source is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(source.read_bytes())
            return True, f"copied:{source.name}"

    if mode in {"auto", "placeholder"}:
        from natural20.image_gen.game_icons import prepare_square_icon, save_pil

        icon = prepare_square_icon(
            render_placeholder_effect_icon(slug, size=size, label=ref.label),
            size,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        save_pil(icon, out, format="PNG")
        return True, "placeholder"

    return False, "no fallback"


def audit_report_as_dict(audit: EffectAssetAudit) -> dict[str, Any]:
    return {
        "ok": audit.ok,
        "invalid_slugs": [
            {
                "class": e.class_name,
                "module": e.module,
                "slug": e.slug,
                "issues": e.issues,
            }
            for e in audit.invalid_slugs
        ],
        "missing_assets": [
            {
                "slug": e.slug,
                "class": e.class_name,
                "module": e.module,
                "expected": str(e.asset_path),
                "fallback": str(
                    effect_fallback_source(e.slug)
                    or "(placeholder or MCP)"
                ),
            }
            for e in audit.missing_assets
        ],
        "effects": [
            {
                "slug": e.slug,
                "class": e.class_name,
                "module": e.module,
                "slug_source": e.slug_source,
                "asset_exists": e.asset_exists,
                "issues": e.issues,
            }
            for e in audit.effects
        ],
    }


def bundled_effect_icons_root() -> Path:
    return webapp_static_root() / "assets" / "effect"
