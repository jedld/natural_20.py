"""Shared metadata for object hover quick-interact buttons (labels, icons, discovery)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION_ICON_DIR = _REPO_ROOT / 'n20-webapp' / 'webapp' / 'static' / 'actions'

# Glyphicon fallbacks when no PNG is available.
_GLYPH_ICON_BY_ACTION: Dict[str, str] = {
    'open': 'folder-open',
    'close': 'remove',
    'unlock': 'log-in',
    'lock': 'lock',
    'loot': 'briefcase',
    'give': 'share',
    'pickup_drop': 'retweet',
    'take': 'hand-up',
    'buzz': 'bell',
    'use': 'play',
}

# Extra slugs beyond interact_action defaults (door/chest hover set).
_BUILTIN_IMAGE_SLUGS: Dict[str, str] = {
    'open': 'interact_open',
    'close': 'interact_close',
    'unlock': 'interact_unlock',
    'lock': 'interact_lock',
    'loot': 'interact_loot',
    'open_chest': 'open_chest',
    'close_chest': 'closed_chest',
}

_INTERACTION_KEY_RE = re.compile(
    r"interactions(?:\.get)?\[\s*['\"]([a-z][a-z0-9_]*)['\"]",
    re.IGNORECASE,
)


def action_icon_dir() -> Path:
    return _ACTION_ICON_DIR


def action_icon_exists(slug: str) -> bool:
    if not slug:
        return False
    return (_ACTION_ICON_DIR / f'{slug}.png').is_file()


def humanize_action_key(action: str) -> str:
    return ' '.join(part.capitalize() for part in str(action).replace('-', '_').split('_') if part)


def glyph_icon_for_action(action: str) -> str:
    if action in _GLYPH_ICON_BY_ACTION:
        return _GLYPH_ICON_BY_ACTION[action]
    if action.endswith('_check'):
        return 'search'
    if action in ('on', 'off'):
        return 'off' if action == 'off' else 'record'
    return 'wrench'


def default_interact_buttons() -> Dict[str, Dict[str, str]]:
    from natural20.actions.interact_action import _DEFAULT_INTERACT_BUTTONS

    return dict(_DEFAULT_INTERACT_BUTTONS)


def button_metadata_for_action(object_entity, action: str) -> Dict[str, Any]:
    """Resolve label/image hints from object YAML ``buttons`` and global defaults."""
    buttons = getattr(object_entity, 'buttons', None) or {}
    meta = dict(buttons.get(action) or {})
    defaults = default_interact_buttons().get(action) or {}
    for key, value in defaults.items():
        meta.setdefault(key, value)
    return meta


def resolve_action_image_slug(object_entity, action: str) -> str | None:
    meta = button_metadata_for_action(object_entity, action)
    explicit = meta.get('image')
    if explicit and action_icon_exists(str(explicit)):
        return str(explicit)
    if explicit:
        return str(explicit)

    for candidate in (f'interact_{action}', action):
        if action_icon_exists(candidate):
            return candidate
    builtin = _BUILTIN_IMAGE_SLUGS.get(action)
    if builtin and action_icon_exists(builtin):
        return builtin
    return None


def resolve_action_label(object_entity, action: str, details: Dict[str, Any] | None = None) -> str:
    details = details or {}
    prompt = details.get('prompt') or details.get('label')
    if prompt:
        return str(prompt)
    meta = button_metadata_for_action(object_entity, action)
    label = meta.get('label')
    if label:
        return str(label)
    object_label = getattr(object_entity, 'label', None)
    if callable(object_label):
        object_label = object_label()
    if action == 'loot' and object_label:
        return f'Loot {object_label}'
    return humanize_action_key(action)


def discover_interaction_keys_in_python(root: Path | None = None) -> Set[str]:
    root = root or (_REPO_ROOT / 'natural20' / 'item_library')
    keys: Set[str] = set()
    for path in root.glob('*.py'):
        text = path.read_text(encoding='utf-8', errors='ignore')
        keys.update(_INTERACTION_KEY_RE.findall(text))
    return keys


def discover_button_actions_from_yaml_tree(tree: Any) -> Set[str]:
    actions: Set[str] = set()
    if isinstance(tree, dict):
        for button in tree.get('buttons') or []:
            if isinstance(button, dict) and button.get('action'):
                actions.add(str(button['action']))
        for state in tree.get('states') or []:
            actions.add(str(state))
        legend = tree.get('legend')
        if isinstance(legend, dict):
            for entry in legend.values():
                actions |= discover_button_actions_from_yaml_tree(entry)
        for key, value in tree.items():
            if key == 'legend':
                continue
            actions |= discover_button_actions_from_yaml_tree(value)
    elif isinstance(tree, list):
        for item in tree:
            actions |= discover_button_actions_from_yaml_tree(item)
    return actions


def discover_interaction_keys_from_map_yml(path: Path) -> Set[str]:
    if not path.is_file():
        return set()
    import yaml

    raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return discover_button_actions_from_yaml_tree(raw)


def discover_interaction_keys_from_objects_yml(path: Path) -> Set[str]:
    if not path.is_file():
        return set()
    import yaml

    raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return discover_button_actions_from_yaml_tree(raw)


def collect_quick_interact_icon_slugs(
    *,
    extra_actions: Iterable[str] | None = None,
    objects_yml_paths: Iterable[Path] | None = None,
    map_yml_paths: Iterable[Path] | None = None,
) -> List[Dict[str, str]]:
    """Return slug/label pairs that quick-interact may reference."""
    actions: Set[str] = set(discover_interaction_keys_in_python())
    actions |= set(default_interact_buttons().keys())
    actions |= set(_BUILTIN_IMAGE_SLUGS.keys())
    if extra_actions:
        actions |= {str(a) for a in extra_actions if a}

    default_paths = [
        _REPO_ROOT / 'templates' / 'items' / 'objects.yml',
        _REPO_ROOT / 'tests' / 'fixtures' / 'items' / 'objects.yml',
    ]
    for path in objects_yml_paths or default_paths:
        actions |= discover_interaction_keys_from_objects_yml(path)

    default_map_paths = [
        _REPO_ROOT / 'tests' / 'fixtures' / 'maps' / 'object_map.yml',
    ]
    for path in map_yml_paths or default_map_paths:
        actions |= discover_interaction_keys_from_map_yml(path)

    refs: List[Dict[str, str]] = []
    for action in sorted(actions):
        meta = default_interact_buttons().get(action) or {}
        slug = meta.get('image') or f'interact_{action}'
        refs.append({
            'action': action,
            'slug': slug,
            'label': meta.get('label') or humanize_action_key(action),
        })
    return refs


def missing_quick_interact_icons(
    *,
    objects_yml_paths: Iterable[Path] | None = None,
    map_yml_paths: Iterable[Path] | None = None,
) -> List[Dict[str, str]]:
    missing: List[Dict[str, str]] = []
    for ref in collect_quick_interact_icon_slugs(
        objects_yml_paths=objects_yml_paths,
        map_yml_paths=map_yml_paths,
    ):
        slug = ref['slug']
        if not action_icon_exists(slug):
            missing.append(ref)
    return missing
