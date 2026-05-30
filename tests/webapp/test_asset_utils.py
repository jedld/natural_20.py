import os
from pathlib import Path

from webapp.blueprints.helpers import asset_utils


def test_asset_url_prefers_minified_when_enabled(tmp_path, monkeypatch):
    static = tmp_path / 'static'
    static.mkdir()
    (static / 'engine.js').write_text('console.log("dev");', encoding='utf-8')
    (static / 'engine.min.js').write_text('console.log("min");', encoding='utf-8')
    manifest = {
        'buildVersion': 'abc123',
        'files': {'engine.js': 'engine.min.js'},
        'versions': {'engine.min.js': 'deadbeef01'},
    }
    (static / 'manifest.assets.json').write_text(
        __import__('json').dumps(manifest),
        encoding='utf-8',
    )

    monkeypatch.setattr(asset_utils, '_STATIC_ROOT', static)
    monkeypatch.setattr(asset_utils, '_MANIFEST_PATH', static / 'manifest.assets.json')
    asset_utils._load_manifest.cache_clear()
    monkeypatch.setenv('N20_USE_MINIFIED_ASSETS', '1')

    assert asset_utils.asset_url('engine.js') == '/engine.min.js?v=deadbeef01'


def test_asset_url_uses_source_in_dev_mode(tmp_path, monkeypatch):
    static = tmp_path / 'static'
    static.mkdir()
    src = static / 'utils.js'
    src.write_text('x = 1;', encoding='utf-8')
    (static / 'utils.min.js').write_text('x=1', encoding='utf-8')

    monkeypatch.setattr(asset_utils, '_STATIC_ROOT', static)
    monkeypatch.setattr(asset_utils, '_MANIFEST_PATH', static / 'manifest.assets.json')
    asset_utils._load_manifest.cache_clear()
    monkeypatch.delenv('N20_USE_MINIFIED_ASSETS', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('FLASK_DEBUG', raising=False)

    url = asset_utils.asset_url('utils.js')
    assert url.startswith('/utils.js?v=')
    assert 'min' not in url.split('?')[0]
