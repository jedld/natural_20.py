"""YAML loading with template inheritance and campaign fallbacks."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

INHERIT_KEYS = frozenset({"inherit", "$inherit", "extends", "$extends"})
ENTRY_INHERIT_KEYS = frozenset({"inherit", "$inherit"})

# Item catalogues merged with bundled templates when a campaign file has no
# explicit top-level inherit directive.
TEMPLATE_MERGE_RESOURCES = frozenset(
    {"weapons", "equipment", "magic_items", "objects", "spells", "equipment_packs"}
)


def templates_root() -> Path:
    """Return the bundled SRD/templates directory shipped with the engine."""
    import os

    import natural20 as n20

    env_root = os.getenv("NATURAL20_TEMPLATES_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    # Editable checkout: repo root sits next to the natural20 package.
    checkout = Path(n20.__file__).resolve().parent.parent / "templates"
    if checkout.is_dir():
        return checkout

    # Wheel/sdist install: data files land under share/natural20/templates.
    try:
        import sysconfig

        installed = Path(sysconfig.get_path("data")) / "natural20" / "templates"
        if installed.is_dir():
            return installed
    except Exception:
        pass

    return checkout


def deep_merge(base: Any, overlay: Any) -> Any:
    """Recursively merge *overlay* onto *base* (overlay wins on conflicts)."""
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return copy.deepcopy(overlay)
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in INHERIT_KEYS:
            continue
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _file_declares_inherit(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        return False
    return any(key in data for key in INHERIT_KEYS)


def _collect_inherit_refs(data: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in INHERIT_KEYS:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            refs.append(value)
        elif isinstance(value, list):
            refs.extend(str(item) for item in value if isinstance(item, str))
    return refs


def resolve_yaml_reference(
    ref: str,
    *,
    source_path: Path,
    campaign_root: Path | None = None,
) -> Path:
    """Resolve an inherit path relative to templates, campaign, or source file."""
    ref = ref.strip()
    if not ref:
        raise FileNotFoundError("Empty YAML inherit reference")

    fragment_split = ref.split("#", 1)
    ref_path = fragment_split[0].strip()
    templates = templates_root()
    candidates: list[Path] = []

    if ref_path.startswith("@templates/"):
        candidates.append(templates / ref_path[len("@templates/") :])
    elif ref_path.startswith("templates/"):
        candidates.append(templates / ref_path[len("templates/") :])

    path_obj = Path(ref_path)
    if path_obj.is_absolute():
        candidates.append(path_obj)

    candidates.append((source_path.parent / ref_path).resolve())

    if campaign_root is not None:
        campaign = Path(campaign_root).resolve()
        candidates.append((campaign / ref_path).resolve())

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved

    raise FileNotFoundError(
        f"Could not resolve YAML inherit reference '{ref}' from {source_path}"
    )


def _strip_meta_keys(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in INHERIT_KEYS}


def _apply_entry_inherits(data: dict[str, Any]) -> dict[str, Any]:
    """Resolve per-entry ``inherit: <base_key>`` within a mapping resource."""
    result = copy.deepcopy(data)
    changed = True
    while changed:
        changed = False
        for key, value in list(result.items()):
            if key in INHERIT_KEYS or not isinstance(value, dict):
                continue
            inherit_ref = None
            for entry_key in ENTRY_INHERIT_KEYS:
                if entry_key in value:
                    inherit_ref = value[entry_key]
                    break
            if not isinstance(inherit_ref, str):
                continue
            base = result.get(inherit_ref)
            if not isinstance(base, dict):
                raise ValueError(
                    f"Entry '{key}' inherits unknown or non-mapping key '{inherit_ref}'"
                )
            overlay = {
                entry_key: entry_value
                for entry_key, entry_value in value.items()
                if entry_key not in ENTRY_INHERIT_KEYS
            }
            merged_entry = deep_merge(base, overlay)
            if merged_entry != result[key]:
                result[key] = merged_entry
                changed = True
    return result


def load_yaml(
    path: str | Path,
    *,
    campaign_root: str | Path | None = None,
    _chain: set[Path] | None = None,
) -> Any:
    """Load a YAML file, applying file-level inherit directives."""
    resolved = Path(path).resolve()
    if _chain is None:
        _chain = set()
    if resolved in _chain:
        raise ValueError(f"Circular YAML inheritance detected at {resolved}")
    chain = set(_chain)
    chain.add(resolved)

    campaign = Path(campaign_root).resolve() if campaign_root is not None else None

    with resolved.open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream)

    if not isinstance(raw, dict):
        return raw

    merged: dict[str, Any] = {}
    for inherit_ref in _collect_inherit_refs(raw):
        parent_path = resolve_yaml_reference(
            inherit_ref,
            source_path=resolved,
            campaign_root=campaign,
        )
        parent_data = load_yaml(parent_path, campaign_root=campaign, _chain=chain)
        if isinstance(parent_data, dict):
            merged = deep_merge(merged, parent_data)

    merged = deep_merge(merged, raw)
    merged = _strip_meta_keys(merged)
    merged = _apply_entry_inherits(merged)
    return merged


def load_campaign_yaml(
    campaign_root: str | Path,
    category: str,
    resource: str,
    *,
    merge_templates: bool = True,
) -> Any:
    """Load ``<campaign>/<category>/<resource>.yml`` with template fallback."""
    campaign = Path(campaign_root).resolve()
    campaign_path = campaign / category / f"{resource}.yml"
    template_path = templates_root() / category / f"{resource}.yml"

    template_data: dict[str, Any] | None = None
    if template_path.is_file():
        template_data = load_yaml(template_path, campaign_root=campaign)
        if not isinstance(template_data, dict):
            template_data = {}

    if campaign_path.is_file():
        campaign_data = load_yaml(campaign_path, campaign_root=campaign)
        if not isinstance(campaign_data, dict):
            return campaign_data
        explicit_inherit = _file_declares_inherit(campaign_path)
        should_merge = (
            merge_templates
            and category == "items"
            and resource in TEMPLATE_MERGE_RESOURCES
            and not explicit_inherit
        )
        if should_merge and template_data is not None:
            return deep_merge(template_data, campaign_data)
        return campaign_data

    if template_data is not None:
        return template_data

    raise FileNotFoundError(
        f"YAML resource not found: {campaign_path} (no template at {template_path})"
    )


def load_campaign_resource_path(
    campaign_root: str | Path,
    relative_path: str,
    *,
    merge_templates: bool = True,
) -> Any:
    """Load a campaign YAML file by path such as ``npcs/goblin.yml``."""
    relative = Path(relative_path)
    if relative.suffix != ".yml":
        relative = relative.with_suffix(".yml")
    category = relative.parent.as_posix() or "."
    resource = relative.stem
    if category == ".":
        campaign = Path(campaign_root).resolve()
        campaign_path = campaign / relative
        template_path = templates_root() / relative
        if campaign_path.is_file():
            return load_yaml(campaign_path, campaign_root=campaign)
        if template_path.is_file():
            return load_yaml(template_path, campaign_root=campaign)
        raise FileNotFoundError(f"YAML resource not found: {campaign_path}")
    return load_campaign_yaml(
        campaign_root,
        category,
        resource,
        merge_templates=merge_templates,
    )
