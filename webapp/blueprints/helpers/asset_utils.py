"""Static asset URLs with optional minified bundles and content-hash cache busting."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_STATIC_ROOT = Path(__file__).resolve().parents[2] / 'static'
_MANIFEST_PATH = _STATIC_ROOT / 'manifest.assets.json'


@lru_cache(maxsize=1)
def _load_manifest() -> dict:
    if not _MANIFEST_PATH.is_file():
        return {}
    try:
        with _MANIFEST_PATH.open(encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def asset_build_version() -> str:
    """Cache-bust token for templates (replaces legacy ``salt``)."""
    manifest = _load_manifest()
    version = manifest.get('buildVersion')
    if version:
        return str(version)
    env_version = os.environ.get('N20_ASSET_VERSION')
    if env_version:
        return env_version
    return 'dev'


def _use_minified_assets() -> bool:
    env = os.environ.get('N20_USE_MINIFIED_ASSETS')
    if env is not None:
        return env.strip().lower() not in ('0', 'false', 'no', 'off', 'disabled')
    flask_env = os.environ.get('FLASK_ENV', '').strip().lower()
    if flask_env == 'production':
        return True
    debug = os.environ.get('FLASK_DEBUG', '').strip().lower()
    if debug in ('0', 'false', 'no', 'off'):
        return True
    return False


def _version_for(relative_path: str) -> str:
    manifest = _load_manifest()
    versions = manifest.get('versions') or {}
    if relative_path in versions:
        return str(versions[relative_path])
    full = _STATIC_ROOT / relative_path
    if full.is_file():
        return str(int(full.stat().st_mtime))
    return asset_build_version()


def _resolve_asset_path(path: str) -> str:
    """Map ``engine.js`` → ``engine.min.js`` when minified builds are enabled."""
    path = path.lstrip('/').replace('\\', '/')
    if not _use_minified_assets():
        return path

    manifest = _load_manifest()
    files = manifest.get('files') or {}
    if path in files:
        min_path = files[path]
        min_full = _STATIC_ROOT / min_path
        src_full = _STATIC_ROOT / path
        if min_full.is_file() and (
            not src_full.is_file()
            or min_full.stat().st_mtime >= src_full.stat().st_mtime
        ):
            return min_path.replace('\\', '/')

    if path.endswith('.js'):
        min_path = path[:-3] + '.min.js'
        min_full = _STATIC_ROOT / min_path
        src_full = _STATIC_ROOT / path
        if min_full.is_file() and (
            not src_full.is_file()
            or min_full.stat().st_mtime >= src_full.stat().st_mtime
        ):
            return min_path
    elif path.endswith('.css'):
        min_path = path[:-4] + '.min.css'
        min_full = _STATIC_ROOT / min_path
        src_full = _STATIC_ROOT / path
        if min_full.is_file() and (
            not src_full.is_file()
            or min_full.stat().st_mtime >= src_full.stat().st_mtime
        ):
            return min_path

    return path


def asset_url(path: str) -> str:
    """Public URL for a static JS/CSS file under ``webapp/static``."""
    resolved = _resolve_asset_path(path)
    version = _version_for(resolved)
    return f'/{resolved}?v={version}'
