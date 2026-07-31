"""Locale key discovery, resolution, and YAML helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import i18n
import yaml

from natural20.yaml_loader import templates_root

_LOCALE_KEY_RE = re.compile(r'^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$', re.I)

_LOCALE_REFERENCE_PATTERNS = (
    re.compile(r"""\.t\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""session\.t\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""i18n\.t\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""['"]disabled_text['"]\s*:\s*['"]([^'"]+)['"]"""),
    re.compile(r"""['"]reason['"]\s*:\s*['"]([^'"]+)['"]"""),
    re.compile(r"""interaction_sound_toast\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""['"]prompt['"]\s*:\s*['"]([^'"]+)['"]"""),
    re.compile(r"""properties\.get\(\s*['"]label['"]\s*,\s*['"]([^'"]+)['"]"""),
    re.compile(r"""self\.t\(\s*f?['"]([^'"]+)['"]"""),
)

_SCAN_ROOTS = (
    'natural20',
    'n20-webapp/webapp',
    'templates',
)

_LOCALE_LANGUAGE_NAMES = {
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'ja': 'Japanese',
    'ko': 'Korean',
    'zh': 'Chinese',
}


def is_locale_key(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or ' ' in text:
        return False
    if text.startswith('(') and text.endswith(')'):
        return False
    return bool(_LOCALE_KEY_RE.match(text))


def resolve_locale_text(
    translator: Optional[Callable[..., str]],
    value: Any,
    *,
    default: Optional[str] = None,
    **options: Any,
) -> Any:
    """Translate ``value`` when it looks like a locale key; otherwise return as-is."""
    if value is None or value == '':
        return value
    if not is_locale_key(value):
        return value

    if translator is None:
        translated = i18n.t(value, default=default or value, **options)
    else:
        try:
            translated = translator(value, **options)
        except TypeError:
            translated = translator(value)

    if translated == value and default is not None:
        return default
    return translated


def ensure_default_locale_paths(*extra_paths: str | Path) -> List[str]:
    """Register bundled template locales and optional campaign paths on i18n."""
    added: List[str] = []
    candidates = [
        templates_root() / 'locales',
        *extra_paths,
    ]
    for path in candidates:
        resolved = Path(path).resolve()
        if not resolved.is_dir():
            continue
        path_str = str(resolved)
        if path_str not in i18n.load_path:
            i18n.load_path.append(path_str)
            added.append(path_str)
    try:
        i18n.set('filename_format', '{locale}.{format}')
    except Exception:
        pass
    return added


def localize_quick_interact_actions(
    actions: List[Dict[str, Any]],
    session: Any,
) -> List[Dict[str, Any]]:
    """Resolve locale keys in door/chest hover quick-action metadata."""
    if not actions:
        return actions
    translator = getattr(session, 't', None)
    localized: List[Dict[str, Any]] = []
    for action in actions:
        entry = dict(action)
        disabled_text = entry.get('disabled_text')
        if disabled_text:
            entry['disabled_text'] = resolve_locale_text(translator, disabled_text)
        label = entry.get('label')
        if label:
            entry['label'] = resolve_locale_text(translator, label)
        localized.append(entry)
    return localized


def load_locale_document(path: Path) -> Tuple[str, Dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(raw, dict):
        raise ValueError(f'Locale file must be a mapping: {path}')
    if len(raw) == 1 and isinstance(next(iter(raw.values())), dict):
        locale_code = next(iter(raw.keys()))
        return str(locale_code), raw[locale_code]
    return path.stem, raw


def save_locale_document(path: Path, locale_code: str, tree: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {locale_code: tree}
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding='utf-8',
    )


def flatten_locale_tree(tree: Dict[str, Any], prefix: str = '') -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in tree.items():
        full_key = f'{prefix}.{key}' if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten_locale_tree(value, full_key))
        else:
            flat[full_key] = value
    return flat


def unflatten_locale_tree(flat: Dict[str, Any]) -> Dict[str, Any]:
    tree: Dict[str, Any] = {}
    for dotted_key, value in sorted(flat.items()):
        parts = dotted_key.split('.')
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return tree


def get_locale_value(tree: Dict[str, Any], key: str) -> Any:
    node: Any = tree
    for part in key.split('.'):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def set_locale_value(tree: Dict[str, Any], key: str, value: Any) -> None:
    parts = key.split('.')
    node = tree
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def discover_locale_files(repo_root: Path, campaign_root: Optional[Path] = None) -> List[Path]:
    files: List[Path] = []
    template_locales = repo_root / 'templates' / 'locales'
    if template_locales.is_dir():
        files.extend(sorted(template_locales.glob('*.yml')))
    if campaign_root is not None:
        campaign_locales = Path(campaign_root) / 'locales'
        if campaign_locales.is_dir():
            files.extend(sorted(campaign_locales.glob('*.yml')))
    user_levels = repo_root / 'user_levels'
    if user_levels.is_dir():
        for campaign_dir in sorted(user_levels.iterdir()):
            campaign_locales = campaign_dir / 'locales'
            if campaign_locales.is_dir():
                files.extend(sorted(campaign_locales.glob('*.yml')))
    tests_locales = repo_root / 'tests' / 'fixtures' / 'locales'
    if tests_locales.is_dir():
        files.extend(sorted(tests_locales.glob('*.yml')))
    # Preserve order but drop duplicates (campaign overrides templates by path)
    seen: Set[str] = set()
    unique: List[Path] = []
    for path in files:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def scan_locale_key_references(repo_root: Path) -> Dict[str, List[Tuple[str, int, str]]]:
    """Return key -> [(file, line_no, line_text), ...] for referenced locale keys."""
    references: Dict[str, List[Tuple[str, int, str]]] = {}
    for root_name in _SCAN_ROOTS:
        scan_root = repo_root / root_name
        if not scan_root.is_dir():
            continue
        for path in scan_root.rglob('*'):
            if path.suffix not in {'.py', '.yml', '.yaml', '.html', '.js'}:
                continue
            if 'node_modules' in path.parts or '.min.' in path.name:
                continue
            try:
                lines = path.read_text(encoding='utf-8').splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            rel_path = str(path.relative_to(repo_root))
            for line_no, line in enumerate(lines, start=1):
                for pattern in _LOCALE_REFERENCE_PATTERNS:
                    for match in pattern.finditer(line):
                        key = match.group(1).strip()
                        if not is_locale_key(key):
                            continue
                        references.setdefault(key, []).append((rel_path, line_no, line.strip()))
    return references


def missing_locale_keys(
    references: Iterable[str],
    locale_tree: Dict[str, Any],
) -> List[str]:
    missing: List[str] = []
    for key in sorted(set(references)):
        value = get_locale_value(locale_tree, key)
        if value is None:
            missing.append(key)
            continue
        if isinstance(value, str) and value.strip() == key:
            missing.append(key)
    return missing


def locale_language_name(locale_code: str) -> str:
    return _LOCALE_LANGUAGE_NAMES.get(locale_code.lower(), locale_code)


def merge_missing_locale_entries(
    locale_tree: Dict[str, Any],
    entries: Dict[str, str],
) -> Dict[str, int]:
    added = 0
    for key, value in entries.items():
        if get_locale_value(locale_tree, key) is not None:
            continue
        set_locale_value(locale_tree, key, value)
        added += 1
    return {'added': added}
