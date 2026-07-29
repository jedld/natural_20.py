"""Scan and generate missing item, spell, and action icons via Image Gen MCP."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image

from natural20.event_manager import EventManager
from natural20.image_gen.campaign_assets import AssetJobResult, load_campaign_meta
from natural20.image_gen.mcp_client import ImageGenMcpClient, default_mcp_url, save_pil
from natural20.image_gen.prompts import (
    ICON_NEGATIVE,
    action_icon_negative,
    action_icon_prompt,
    campaign_asset_mood,
    effect_icon_prompt,
    item_icon_negative,
    item_icon_prompt,
    spell_icon_prompt,
)
from natural20.image_gen.spell_scroll_icons import (
    is_spell_scroll_item,
    render_spell_scroll_icon,
    spell_scroll_spell_slug,
)
from natural20.image_gen.web_optimize import optimize_icon_for_web
from natural20.session import Session
from natural20.utils.spell_loader import spell_is_implemented

GenerateFn = Callable[..., Any]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_N20_WEBAPP_STATIC = _REPO_ROOT / "n20-webapp" / "webapp" / "static"
_LEGACY_WEBAPP_STATIC = _REPO_ROOT / "webapp" / "static"
_WEBAPP_STATIC = (
    _N20_WEBAPP_STATIC if _N20_WEBAPP_STATIC.is_dir() else _LEGACY_WEBAPP_STATIC
)


def webapp_static_root() -> Path:
    return _WEBAPP_STATIC


def bundled_item_path(image_name: str, ext: str = ".png") -> Path | None:
    path = _WEBAPP_STATIC / "assets" / "items" / f"{image_name}{ext}"
    return path if path.is_file() else None


@dataclass
class IconAssetRef:
    kind: str  # "item" | "spell" | "action" | "effect"
    key: str
    label: str
    image_name: str
    output_path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    source: str = ""


@dataclass
class GameIconReport:
    results: list[AssetJobResult] = field(default_factory=list)
    scanned: int = 0
    missing: int = 0

    @property
    def errors(self) -> list[AssetJobResult]:
        return [r for r in self.results if r.error]

    @property
    def written(self) -> list[AssetJobResult]:
        return [r for r in self.results if not r.skipped and not r.error]


def _repo_root() -> Path:
    return _REPO_ROOT


def item_icon_exists(image_name: str, *, campaign_root: Path | None = None) -> bool:
    for ext in (".png", ".webp"):
        if bundled_item_path(image_name, ext) is not None:
            return True
        if campaign_root is not None:
            path = campaign_root / "assets" / "items" / f"{image_name}{ext}"
            if path.is_file():
                return True
    return False


def spell_icon_path(spell_id: str, *, spell_output_dir: Path | None = None) -> Path:
    base = spell_output_dir or (webapp_static_root() / "spells")
    return base / f"spell_{spell_id}.png"


def spell_icon_exists(spell_id: str, *, spell_output_dir: Path | None = None) -> bool:
    return spell_icon_path(spell_id, spell_output_dir=spell_output_dir).is_file()


def default_item_output_dir(*, campaign_root: Path | None, write_to: str) -> Path:
    if write_to == "campaign":
        if campaign_root is None:
            raise ValueError("write_to=campaign requires a campaign root")
        return campaign_root / "assets" / "items"
    return webapp_static_root() / "assets" / "items"


def default_spell_output_dir() -> Path:
    return webapp_static_root() / "spells"


def default_action_output_dir() -> Path:
    return webapp_static_root() / "actions"


def default_effect_output_dir() -> Path:
    return webapp_static_root() / "assets" / "effect"


_EFFECT_ICON_TYPES = frozenset({"buff", "debuff", "control", "transmutation", "summon"})

# Non-spell tile effects (engulf, etc.) that still need bundled icons.
_EXTRA_EFFECT_SLUGS = frozenset({"engulf"})


def spell_needs_effect_icon(meta: dict[str, Any]) -> bool:
    if meta.get("concentration"):
        return True
    spell_type = str(meta.get("type") or "").lower()
    return spell_type in _EFFECT_ICON_TYPES


def effect_icon_path(effect_id: str, *, effect_output_dir: Path | None = None) -> Path:
    base = effect_output_dir or default_effect_output_dir()
    return base / f"{effect_id}.png"


def effect_icon_exists(effect_id: str, *, effect_output_dir: Path | None = None) -> bool:
    return effect_icon_path(effect_id, effect_output_dir=effect_output_dir).is_file()


_ACTION_BUILD_BLOCKLIST = frozenset(
    {
        "param",
        "opts",
        "source",
        "session",
        "instant",
        "attack",
        "has_channel_divinity",
        "is_raging",
        "second_wind_count",
        "action_surge_count",
        "speak",
    }
)

# Icons used by the web UI but not always discoverable from Action.build() literals.
_EXTRA_ACTION_ICON_SLUGS = frozenset(
    {
        "action_surge",
        "attack_melee",
        "attack_ranged",
        "attack_second",
        "attack_thrown",
        "bardic_inspiration",
        "closed_chest",
        "dash_bonus",
        "disengage_bonus",
        "dismiss_familiar",
        "divine_smite",
        "dodge",
        "drop_grapple",
        "flurry_of_blows",
        "hide_bonus",
        "interact_close",
        "interact_give",
        "interact_light",
        "interact_lock",
        "interact_lockpick",
        "interact_loot",
        "interact_open",
        "interact_pickup_drop",
        "interact_unlock",
        "inventory",
        "open_chest",
        "patient_defense",
        "push",
        "reckless_attack",
        "step_of_the_wind",
        "two_weapon_attack",
        "two_weapon_attack_second",
        "two_weapon_attack_thrown",
        "wild_shape",
    }
)


def discover_action_types_from_modules() -> set[str]:
    actions_dir = _REPO_ROOT / "natural20" / "actions"
    found: set[str] = set()
    pattern = re.compile(
        r"(?:Action|build)\(\s*session,\s*(?:source|self\.source),\s*['\"]([a-z][a-z0-9_]*)['\"]"
    )
    for path in actions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            slug = match.group(1)
            if slug not in _ACTION_BUILD_BLOCKLIST:
                found.add(slug)
    return found


def discover_object_button_images(session: Session) -> set[str]:
    images: set[str] = set()
    try:
        objects = session.load_yaml_file("items", "objects")
    except FileNotFoundError:
        return images
    if not isinstance(objects, dict):
        return images
    for meta in objects.values():
        if not isinstance(meta, dict):
            continue
        for button in meta.get("buttons") or []:
            if not isinstance(button, dict):
                continue
            image = button.get("image")
            if image:
                images.add(str(image))
            action = button.get("action")
            if action:
                images.add(f"interact_{action}")
    return images


def collect_action_icon_slugs(session: Session | None = None) -> set[str]:
    slugs = set(_EXTRA_ACTION_ICON_SLUGS)
    slugs |= discover_action_types_from_modules()
    slugs.add("attack")
    if session is not None:
        slugs |= discover_object_button_images(session)
    return {slug for slug in slugs if slug and " " not in slug}


def action_icon_exists(slug: str, *, action_output_dir: Path | None = None) -> bool:
    base = action_output_dir or default_action_output_dir()
    return (base / f"{slug}.png").is_file()


def discover_action_refs(
    session: Session,
    *,
    action_output_dir: Path | None = None,
) -> list[IconAssetRef]:
    out_dir = action_output_dir or default_action_output_dir()
    refs: list[IconAssetRef] = []
    for slug in sorted(collect_action_icon_slugs(session)):
        label = slug.replace("_", " ").title()
        refs.append(
            IconAssetRef(
                kind="action",
                key=slug,
                label=label,
                image_name=slug,
                output_path=out_dir / f"{slug}.png",
                meta={"slug": slug, "description": label},
                source="actions",
            )
        )
    return refs


def resolve_item_image_name(key: str, meta: dict[str, Any]) -> str:
    for field in ("image", "token_image", "profile_image"):
        value = meta.get(field)
        if value:
            return str(value)
    return str(key)


def object_entry_has_icon(meta: dict[str, Any]) -> bool:
    return any(meta.get(field) for field in ("image", "token_image", "profile_image"))


def discover_item_refs(
    session: Session,
    *,
    campaign_root: Path | None = None,
    item_output_dir: Path | None = None,
    include_objects: bool = False,
    include_packs: bool = False,
) -> list[IconAssetRef]:
    catalogs: list[tuple[str, dict[str, Any] | None]] = [
        ("weapons", session.load_weapons()),
        ("equipment", session.load_yaml_file("items", "equipment")),
        ("magic_items", session.load_all_magic_items()),
    ]
    if include_packs:
        catalogs.append(("equipment_packs", session.load_yaml_file("items", "equipment_packs")))
    if include_objects:
        catalogs.append(("objects", session.load_yaml_file("items", "objects")))
    out_dir = item_output_dir or default_item_output_dir(
        campaign_root=campaign_root, write_to="bundled"
    )
    refs: list[IconAssetRef] = []
    seen: set[str] = set()
    for source, catalog in catalogs:
        if not isinstance(catalog, dict):
            continue
        for key, meta in catalog.items():
            if not key or not isinstance(meta, dict):
                continue
            if source == "objects" and not object_entry_has_icon(meta):
                continue
            image_name = resolve_item_image_name(str(key), meta)
            if image_name in seen:
                continue
            seen.add(image_name)
            label = str(
                meta.get("label")
                or meta.get("name")
                or meta.get("item_class")
                or key
            )
            refs.append(
                IconAssetRef(
                    kind="item",
                    key=str(key),
                    label=label,
                    image_name=image_name,
                    output_path=out_dir / f"{image_name}.png",
                    meta=meta,
                    source=source,
                )
            )
    return refs


def discover_spell_refs(
    session: Session,
    *,
    spell_output_dir: Path | None = None,
) -> list[IconAssetRef]:
    spells = session.load_all_spells()
    if not isinstance(spells, dict):
        return []
    out_dir = spell_output_dir or default_spell_output_dir()
    refs: list[IconAssetRef] = []
    for key, meta in spells.items():
        if not key or not isinstance(meta, dict):
            continue
        if not spell_is_implemented(str(key), meta):
            continue
        refs.append(
            IconAssetRef(
                kind="spell",
                key=str(key),
                label=str(meta.get("label") or meta.get("name") or key),
                image_name=f"spell_{key}",
                output_path=out_dir / f"spell_{key}.png",
                meta=meta,
                source="spells",
            )
        )
    return refs


def discover_effect_refs(
    session: Session,
    *,
    effect_output_dir: Path | None = None,
) -> list[IconAssetRef]:
    spells = session.load_all_spells()
    if not isinstance(spells, dict):
        return []
    out_dir = effect_output_dir or default_effect_output_dir()
    refs: list[IconAssetRef] = []
    seen: set[str] = set()
    for key, meta in spells.items():
        if not key or not isinstance(meta, dict):
            continue
        if not spell_is_implemented(str(key), meta):
            continue
        if not spell_needs_effect_icon(meta):
            continue
        slug = str(key)
        if slug in seen:
            continue
        seen.add(slug)
        refs.append(
            IconAssetRef(
                kind="effect",
                key=slug,
                label=str(meta.get("label") or meta.get("name") or slug),
                image_name=slug,
                output_path=out_dir / f"{slug}.png",
                meta=meta,
                source="effects",
            )
        )
    for slug in sorted(_EXTRA_EFFECT_SLUGS):
        if slug in seen:
            continue
        seen.add(slug)
        refs.append(
            IconAssetRef(
                kind="effect",
                key=slug,
                label=slug.replace("_", " ").title(),
                image_name=slug,
                output_path=out_dir / f"{slug}.png",
                meta={"slug": slug},
                source="effects",
            )
        )
    return refs


def scan_missing_icons(
    session: Session,
    *,
    items: bool = True,
    spells: bool = True,
    actions: bool = True,
    effects: bool = True,
    campaign_root: Path | None = None,
    item_output_dir: Path | None = None,
    spell_output_dir: Path | None = None,
    action_output_dir: Path | None = None,
    effect_output_dir: Path | None = None,
    only: Iterable[str] | None = None,
    force: bool = False,
    include_objects: bool = False,
    include_packs: bool = False,
) -> list[IconAssetRef]:
    only_set = {x.lower() for x in only} if only else None
    missing: list[IconAssetRef] = []
    if items:
        for ref in discover_item_refs(
            session,
            campaign_root=campaign_root,
            item_output_dir=item_output_dir,
            include_objects=include_objects,
            include_packs=include_packs,
        ):
            if only_set and ref.key.lower() not in only_set and ref.image_name.lower() not in only_set:
                continue
            if not force and item_icon_exists(ref.image_name, campaign_root=campaign_root):
                continue
            missing.append(ref)
    if spells:
        for ref in discover_spell_refs(session, spell_output_dir=spell_output_dir):
            if only_set and ref.key.lower() not in only_set:
                continue
            if not force and spell_icon_exists(ref.key, spell_output_dir=spell_output_dir):
                continue
            missing.append(ref)
    if actions:
        for ref in discover_action_refs(session, action_output_dir=action_output_dir):
            if only_set and ref.key.lower() not in only_set and ref.image_name.lower() not in only_set:
                continue
            if not force and action_icon_exists(ref.key, action_output_dir=action_output_dir):
                continue
            missing.append(ref)
    if effects:
        for ref in discover_effect_refs(session, effect_output_dir=effect_output_dir):
            if only_set and ref.key.lower() not in only_set:
                continue
            if not force and effect_icon_exists(ref.key, effect_output_dir=effect_output_dir):
                continue
            missing.append(ref)
    return missing


def prepare_square_icon(image: Image.Image, size: int) -> Image.Image:
    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA")
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (24, 20, 28))
        background.paste(image, mask=image.split()[-1])
        image = background
    else:
        image = image.convert("RGB")
    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image


def _prompt_for_ref(ref: IconAssetRef, *, icon_style: str, theme: str) -> str:
    custom = str(ref.meta.get("image_prompt") or ref.meta.get("icon_prompt") or "").strip()
    if custom:
        from natural20.image_gen.prompts import fit_clip_prompt

        return fit_clip_prompt(custom, icon_style)
    if ref.kind == "spell":
        # Bundled spell icons are global UI assets — skip campaign mood/description.
        return spell_icon_prompt(
            name=ref.key,
            label=ref.label,
            school=str(ref.meta.get("school") or ""),
            icon_style=icon_style,
        )
    if ref.kind == "effect":
        return effect_icon_prompt(
            name=ref.key,
            label=ref.label,
            school=str(ref.meta.get("school") or ""),
            icon_style=icon_style,
        )
    if ref.kind == "action":
        return action_icon_prompt(
            slug=ref.key,
            label=ref.label,
            description=str(ref.meta.get("description") or ""),
            icon_style=icon_style,
            theme=theme,
        )
    return item_icon_prompt(
        name=ref.key,
        label=ref.label,
        item_type=str(ref.meta.get("type") or ref.meta.get("item_class") or ""),
        subtype=str(ref.meta.get("subtype") or ""),
        icon_style=icon_style,
    )


def _negative_for_ref(ref: IconAssetRef) -> str:
    if ref.kind == "action":
        return action_icon_negative(slug=ref.key)
    if ref.kind != "item":
        return ICON_NEGATIVE
    if is_spell_scroll_item(ref.meta):
        return ICON_NEGATIVE
    extra = item_icon_negative(
        name=ref.key,
        label=ref.label,
        item_type=str(ref.meta.get("type") or ref.meta.get("item_class") or ""),
    )
    return extra or ICON_NEGATIVE


def _try_render_spell_scroll_icon(
    ref: IconAssetRef,
    *,
    spell_output_dir: Path | None,
    item_size: int,
) -> Image.Image:
    spell_slug = spell_scroll_spell_slug(ref.meta)
    if not spell_slug:
        raise ValueError(f"Spell scroll item missing spell slug: {ref.key}")
    spell_icon = spell_icon_path(spell_slug, spell_output_dir=spell_output_dir)
    icon = render_spell_scroll_icon(spell_slug=spell_slug, spell_icon_path=spell_icon)
    return prepare_square_icon(icon, item_size)


def generate_game_icons(
    *,
    session: Session,
    missing: list[IconAssetRef],
    generator: GenerateFn | None = None,
    client: ImageGenMcpClient | None = None,
    mcp_url: str | None = None,
    icon_style: str = "",
    theme: str = "",
    force: bool = False,
    dry_run: bool = False,
    quality: str = "medium",
    model: str | None = None,
    item_size: int = 128,
    spell_size: int = 128,
    action_size: int = 128,
    effect_size: int = 128,
    limit: int | None = None,
    optimize: bool = True,
    webp: bool = False,
    webp_quality: int = 82,
    spell_output_dir: Path | None = None,
) -> GameIconReport:
    report = GameIconReport(scanned=len(missing), missing=len(missing))
    if not missing:
        return report

    if not theme and getattr(session, "root_path", None):
        meta = load_campaign_meta(Path(session.root_path))
        theme = campaign_asset_mood(meta)

    owns_client = False
    if generator is None:
        if client is None:
            client = ImageGenMcpClient(mcp_url or default_mcp_url())
            owns_client = True
            client.initialize()

        def _gen(**kwargs):
            if model and "model" not in kwargs:
                kwargs["model"] = model
            return client.generate_image(**kwargs)

        generator = _gen

    try:
        jobs = missing[:limit] if limit else missing
        for ref in jobs:
            out = ref.output_path
            if out.is_file() and not force:
                report.results.append(
                    AssetJobResult(ref.kind, ref.key, out, skipped=True, reason="exists")
                )
                continue

            prompt = _prompt_for_ref(ref, icon_style=icon_style, theme=theme)
            if dry_run:
                if ref.kind == "item" and is_spell_scroll_item(ref.meta):
                    spell_slug = spell_scroll_spell_slug(ref.meta)
                    reason = f"dry-run: spell-scroll-composite ({spell_slug})"
                else:
                    reason = f"dry-run: {prompt[:96]}"
                report.results.append(
                    AssetJobResult(
                        ref.kind,
                        ref.key,
                        out,
                        skipped=True,
                        reason=reason,
                    )
                )
                continue

            try:
                target_size = {
                    "spell": spell_size,
                    "action": action_size,
                    "effect": effect_size,
                }.get(ref.kind, item_size)
                if ref.kind == "item" and is_spell_scroll_item(ref.meta):
                    icon = _try_render_spell_scroll_icon(
                        ref,
                        spell_output_dir=spell_output_dir,
                        item_size=target_size,
                    )
                    out.parent.mkdir(parents=True, exist_ok=True)
                    save_pil(icon, out, format="PNG")
                    opt_note = "spell-scroll-composite"
                else:
                    generated = generator(
                        prompt=prompt,
                        size="512x512",
                        quality=quality,
                        negative_prompt=_negative_for_ref(ref),
                        output_format="png",
                    )
                    icon = prepare_square_icon(generated.image, target_size)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    save_pil(icon, out, format="PNG")
                    opt_note = ""
                if optimize:
                    try:
                        stats = optimize_icon_for_web(
                            out,
                            max_dim=target_size,
                            webp=webp,
                            webp_quality=webp_quality,
                        )
                        saved = stats["bytes_before"] - stats["bytes_after"]
                        if saved > 0:
                            opt_note = f"optimized (-{saved} bytes)"
                        if stats.get("webp"):
                            opt_note = f"{opt_note}, webp".strip(", ")
                    except Exception as exc:  # noqa: BLE001 — keep generated asset
                        opt_note = f"optimize-warning: {exc}"
                report.results.append(
                    AssetJobResult(ref.kind, ref.key, out, reason=opt_note or "")
                )
            except Exception as exc:  # noqa: BLE001 — collect per-icon failures
                report.results.append(
                    AssetJobResult(ref.kind, ref.key, out, error=str(exc))
                )
    finally:
        if owns_client and client is not None:
            client.close()

    return report


def build_session(root: str | Path) -> Session:
    return Session(root_path=str(root), event_manager=EventManager())


def run_icon_generation(
    *,
    root: str | Path,
    items: bool = True,
    spells: bool = True,
    actions: bool = True,
    effects: bool = True,
    write_to: str = "bundled",
    only: Iterable[str] | None = None,
    item_output_dir: Path | None = None,
    spell_output_dir: Path | None = None,
    action_output_dir: Path | None = None,
    effect_output_dir: Path | None = None,
    **kwargs: Any,
) -> GameIconReport:
    root_path = Path(root).resolve()
    session = build_session(root_path)
    campaign_root = root_path if (root_path / "game.yml").is_file() or (root_path / "index.json").is_file() else None
    if item_output_dir is None:
        item_output_dir = default_item_output_dir(campaign_root=campaign_root, write_to=write_to)
    if spell_output_dir is None:
        spell_output_dir = default_spell_output_dir()
    if action_output_dir is None:
        action_output_dir = default_action_output_dir()
    if effect_output_dir is None:
        effect_output_dir = default_effect_output_dir()

    include_objects = bool(kwargs.pop("include_objects", False))
    include_packs = bool(kwargs.pop("include_packs", False))

    missing = scan_missing_icons(
        session,
        items=items,
        spells=spells,
        actions=actions,
        effects=effects,
        campaign_root=campaign_root,
        item_output_dir=item_output_dir,
        spell_output_dir=spell_output_dir,
        action_output_dir=action_output_dir,
        effect_output_dir=effect_output_dir,
        only=only,
        force=bool(kwargs.get("force")),
        include_objects=include_objects,
        include_packs=include_packs,
    )
    return generate_game_icons(
        session=session,
        missing=missing,
        spell_output_dir=spell_output_dir,
        **kwargs,
    )
