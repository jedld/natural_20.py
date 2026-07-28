"""Editor icon path resolution for template vs campaign object scopes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from natural20.yaml_loader import INHERIT_KEYS, templates_root

_REPO_ROOT = Path(__file__).resolve().parents[2]


def bundled_editor_dir() -> Path:
    return _REPO_ROOT / "webapp" / "static" / "assets" / "editor"


def templates_editor_dir() -> Path:
    return templates_root() / "assets" / "editor"


def campaign_editor_dir(campaign_root: str | Path) -> Path:
    return Path(campaign_root).resolve() / "assets" / "editor"


def is_campaign_root(path: str | Path | None) -> bool:
    if not path:
        return False
    root = Path(path).resolve()
    return (root / "game.yml").is_file() or (root / "index.json").is_file()


def default_editor_output_dir(campaign_root: str | Path | None = None) -> Path:
    if is_campaign_root(campaign_root):
        return campaign_editor_dir(campaign_root)  # type: ignore[arg-type]
    return templates_editor_dir()


def _load_objects_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(key): value
        for key, value in data.items()
        if str(key) not in INHERIT_KEYS and isinstance(value, dict)
    }


def load_template_objects() -> dict[str, Any]:
    return _load_objects_yaml(templates_root() / "items" / "objects.yml")


def load_campaign_objects_file(campaign_root: str | Path) -> dict[str, Any]:
    return _load_objects_yaml(Path(campaign_root).resolve() / "items" / "objects.yml")


def object_editor_scope(object_id: str, *, campaign_root: str | Path | None = None) -> str:
    """Return ``template`` or ``campaign`` for where an object's editor icon belongs."""
    template_ids = set(load_template_objects())
    if object_id in template_ids:
        return "template"
    if campaign_root and object_id in load_campaign_objects_file(campaign_root):
        return "campaign"
    if campaigns_defining_object(object_id):
        return "campaign"
    return "template"


def editor_output_dir_for_object(
    object_id: str,
    *,
    campaign_root: str | Path | None = None,
) -> Path:
    scope = object_editor_scope(object_id, campaign_root=campaign_root)
    if scope == "campaign":
        if campaign_root:
            return campaign_editor_dir(campaign_root)
        roots = campaigns_defining_object(object_id)
        if len(roots) == 1:
            return campaign_editor_dir(roots[0])
    return templates_editor_dir()


def editor_icon_path(
    filename: str,
    *,
    campaign_root: str | Path | None = None,
) -> Path:
    name = filename if filename.endswith(".png") else f"{filename}.png"
    object_id = Path(name).stem
    return editor_output_dir_for_object(object_id, campaign_root=campaign_root) / name


def editor_icon_exists(
    filename: str,
    *,
    campaign_root: str | Path | None = None,
) -> bool:
    name = filename if filename.endswith(".png") else f"{filename}.png"
    object_id = Path(name).stem
    search_dirs = []
    if campaign_root:
        search_dirs.append(campaign_editor_dir(campaign_root))
    search_dirs.extend([templates_editor_dir(), bundled_editor_dir()])
    scope_dir = editor_output_dir_for_object(object_id, campaign_root=campaign_root)
    if scope_dir not in search_dirs:
        search_dirs.insert(0, scope_dir)
    return any((directory / name).is_file() for directory in search_dirs)


def campaigns_defining_object(object_id: str) -> list[Path]:
    """Campaign roots whose raw ``items/objects.yml`` defines *object_id*."""
    template_ids = set(load_template_objects())
    if object_id in template_ids:
        return []
    roots: list[Path] = []
    user_levels = _REPO_ROOT / "user_levels"
    if not user_levels.is_dir():
        return roots
    for objects_path in sorted(user_levels.glob("*/items/objects.yml")):
        campaign_root = objects_path.parent.parent
        if object_id in load_campaign_objects_file(campaign_root):
            roots.append(campaign_root)
    return roots


def resolve_object_id_from_editor_filename(filename: str) -> str | None:
    """Map an editor PNG filename to a known objects.yml key when possible."""
    stem = Path(filename).stem
    template_ids = set(load_template_objects())
    if stem in template_ids:
        return stem
    campaign_ids: set[str] = set()
    user_levels = _REPO_ROOT / "user_levels"
    if user_levels.is_dir():
        for objects_path in user_levels.glob("*/items/objects.yml"):
            campaign_ids.update(load_campaign_objects_file(objects_path.parent.parent))
    if stem in campaign_ids:
        return stem
    known_ids = sorted(template_ids | campaign_ids, key=len, reverse=True)
    for object_id in known_ids:
        if stem == object_id or stem.startswith(f"{object_id}_"):
            return object_id
    return None


def migrate_bundled_editor_icon(
    filename: str,
    *,
    move: bool = True,
    dry_run: bool = False,
) -> list[tuple[Path, Path]]:
    """Move/copy a bundled editor PNG to template or campaign asset dirs."""
    source = bundled_editor_dir() / filename
    if not source.is_file():
        return []

    object_id = resolve_object_id_from_editor_filename(filename)
    if not object_id:
        return []

    scope = object_editor_scope(object_id)
    targets: list[Path] = []
    if scope == "template":
        targets.append(templates_editor_dir() / filename)
    else:
        campaign_roots = campaigns_defining_object(object_id)
        if not campaign_roots:
            return []
        targets.extend(campaign_editor_dir(root) / filename for root in campaign_roots)

    moves: list[tuple[Path, Path]] = []
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        moves.append((source, target))
        if dry_run:
            continue
        if move and len(targets) == 1:
            source.replace(target)
            source = target
        else:
            target.write_bytes(source.read_bytes())
    if move and len(targets) > 1 and source.is_file() and not dry_run:
        source.unlink()
    return moves


def migrate_bundled_editor_icons(*, move: bool = True, dry_run: bool = False) -> list[tuple[Path, Path]]:
    """Relocate all bundled editor PNGs into template or campaign folders."""
    bundled = bundled_editor_dir()
    if not bundled.is_dir():
        return []
    results: list[tuple[Path, Path]] = []
    for path in sorted(bundled.glob("*.png")):
        results.extend(
            migrate_bundled_editor_icon(path.name, move=move, dry_run=dry_run)
        )
    return results


def redistribute_template_editor_icons(*, dry_run: bool = False) -> list[tuple[Path, Path]]:
    """Move campaign-scoped icons out of templates/assets/editor into campaigns."""
    template_dir = templates_editor_dir()
    if not template_dir.is_dir():
        return []
    moves: list[tuple[Path, Path]] = []
    for path in sorted(template_dir.glob("*.png")):
        object_id = resolve_object_id_from_editor_filename(path.name)
        if not object_id or object_editor_scope(object_id) != "campaign":
            continue
        campaign_roots = campaigns_defining_object(object_id)
        if not campaign_roots:
            continue
        for root in campaign_roots:
            target = campaign_editor_dir(root) / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            moves.append((path, target))
            if dry_run:
                continue
            if len(campaign_roots) == 1:
                path.replace(target)
                path = target
            else:
                target.write_bytes(path.read_bytes())
        if not dry_run and len(campaign_roots) > 1 and path.is_file():
            path.unlink()
    return moves
