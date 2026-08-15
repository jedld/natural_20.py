"""Item icon path resolution for template vs campaign (and import/expansion) scope.

Campaign-only items — keys that exist in a campaign (or imported campaign /
expansion pack) catalogue but not in bundled ``templates/items/`` — store their
icons under that owner's ``assets/items/``. Generic SRD items keep bundled
``webapp/static/assets/items/`` art.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Literal

import yaml

from natural20.yaml_loader import (
    INHERIT_KEYS,
    TEMPLATE_MERGE_RESOURCES,
    campaign_import_roots,
    expansion_pack_roots,
    templates_root,
)

ItemScope = Literal["template", "campaign", "expansion"]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_N20_WEBAPP_STATIC = _REPO_ROOT / "n20-webapp" / "webapp" / "static"
_LEGACY_WEBAPP_STATIC = _REPO_ROOT / "webapp" / "static"

ITEM_CATALOG_STEMS = frozenset(TEMPLATE_MERGE_RESOURCES)


def webapp_static_root() -> Path:
    return _N20_WEBAPP_STATIC if _N20_WEBAPP_STATIC.is_dir() else _LEGACY_WEBAPP_STATIC


def bundled_item_dir() -> Path:
    return webapp_static_root() / "assets" / "items"


def campaign_item_dir(campaign_root: str | Path) -> Path:
    return Path(campaign_root).resolve() / "assets" / "items"


def is_campaign_root(path: str | Path | None) -> bool:
    if not path:
        return False
    root = Path(path).resolve()
    return (root / "game.yml").is_file() or (root / "index.json").is_file()


def _keys_from_items_yaml(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError:
        return set()
    if not isinstance(data, dict):
        return set()
    return {
        str(key)
        for key, value in data.items()
        if str(key) not in INHERIT_KEYS and isinstance(value, dict)
    }


def _catalog_item_ids(root: str | Path) -> set[str]:
    base = Path(root).resolve() / "items"
    ids: set[str] = set()
    for stem in ITEM_CATALOG_STEMS:
        ids |= _keys_from_items_yaml(base / f"{stem}.yml")
    return ids


def template_item_ids() -> set[str]:
    """Item ids defined in bundled templates and ruleset overlays."""
    ids = _catalog_item_ids(templates_root())
    rulesets = templates_root() / "rulesets"
    if rulesets.is_dir():
        for overlay in rulesets.glob("*/items/*.yml"):
            if overlay.stem in ITEM_CATALOG_STEMS:
                ids |= _keys_from_items_yaml(overlay)
    return ids


def campaign_item_ids(campaign_root: str | Path) -> set[str]:
    """Top-level item keys in a campaign (or expansion pack) items/*.yml."""
    return _catalog_item_ids(campaign_root)


def item_definition_owner(
    item_id: str,
    *,
    campaign_root: str | Path | None = None,
    template_ids: set[str] | None = None,
) -> tuple[ItemScope, Path | None]:
    """Return ``(scope, owner_root)`` for where *item_id* is defined.

    Template / ruleset keys are ``("template", None)``. Campaign-only keys
    return the campaign, imported campaign, or expansion-pack directory that
    declares them.
    """
    ids = template_item_ids() if template_ids is None else template_ids
    if item_id in ids:
        return "template", None
    if not campaign_root:
        return "template", None
    campaign = Path(campaign_root).resolve()
    if item_id in campaign_item_ids(campaign):
        return "campaign", campaign
    for import_root in campaign_import_roots(campaign):
        if item_id in campaign_item_ids(import_root):
            return "campaign", import_root
    for pack_root in expansion_pack_roots(campaign):
        if item_id in campaign_item_ids(pack_root):
            return "expansion", pack_root
    return "template", None


def item_icon_scope(
    item_id: str,
    *,
    campaign_root: str | Path | None = None,
    template_ids: set[str] | None = None,
) -> ItemScope:
    scope, _owner = item_definition_owner(
        item_id,
        campaign_root=campaign_root,
        template_ids=template_ids,
    )
    return scope


def item_icon_output_dir(
    item_id: str,
    *,
    campaign_root: str | Path | None = None,
    write_to: str = "auto",
    template_ids: set[str] | None = None,
) -> Path:
    """Directory that should own the PNG for *item_id*.

    Campaign-only items always write to the defining campaign/expansion
    ``assets/items/`` — never into bundled webapp static — even when
    ``write_to=bundled``. ``write_to=campaign`` forces template items into the
    current campaign as optional overrides.
    """
    scope, owner = item_definition_owner(
        item_id,
        campaign_root=campaign_root,
        template_ids=template_ids,
    )
    if scope in {"campaign", "expansion"} and owner is not None:
        return campaign_item_dir(owner)
    if write_to == "campaign" and campaign_root:
        return campaign_item_dir(campaign_root)
    return bundled_item_dir()


def iter_campaign_asset_roots(campaign_root: str | Path | None) -> Iterable[Path]:
    """Current campaign, then imports (earlier first), then expansion packs."""
    if not campaign_root:
        return
    campaign = Path(campaign_root).resolve()
    yield campaign
    yield from campaign_import_roots(campaign)
    yield from expansion_pack_roots(campaign)


def resolve_item_icon_file(
    filename: str,
    *,
    campaign_root: str | Path | None = None,
    default_ext: str = ".png",
) -> Path | None:
    """Locate an item icon: campaign/imports/packs first, then bundled, then templates."""
    name = filename
    if default_ext and not Path(name).suffix:
        name = f"{name}{default_ext}"

    for root in iter_campaign_asset_roots(campaign_root):
        path = root / "assets" / "items" / name
        if path.is_file():
            return path

    bundled = bundled_item_dir() / name
    if bundled.is_file():
        return bundled

    template = templates_root() / "assets" / "items" / name
    if template.is_file():
        return template
    return None


def item_icon_exists_at_scope(
    image_name: str,
    *,
    item_id: str | None = None,
    campaign_root: str | Path | None = None,
    write_to: str = "auto",
) -> bool:
    """True when the icon exists in the directory that should own it."""
    key = item_id or image_name
    out_dir = item_icon_output_dir(key, campaign_root=campaign_root, write_to=write_to)
    stem = Path(image_name).stem
    return any((out_dir / f"{stem}{ext}").is_file() for ext in (".png", ".webp"))
