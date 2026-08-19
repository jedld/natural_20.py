"""Campaign 3D model catalog for the Three.js VTT.

Campaigns may define meshes in ``vtt3d.yml`` (or ``game.yml`` → ``vtt3d``)
and/or a ``vtt3d:`` block on an object or legend entry. The engine never
hard-codes campaign names; built-in inference only uses generic type/name
tokens such as ``portcullis`` and ``secret_door``.

Resolution (highest wins):

1. Object/legend ``vtt3d:`` block
2. Campaign catalog keyed by object ``type``, then ``name``
3. Built-in inference for doors (secret → ``secret_door``, portcullis →
   ``portcullis``, window wall → ``window``, otherwise ``door``) and floor hatches (``trap_door``,
   ``secret_trapdoor``, ``pit_trap``)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from natural20.yaml_loader import load_yaml

DOOR_KINDS = frozenset({'door', 'secret_door', 'portcullis', 'window', 'wall', 'skip'})
HATCH_KINDS = frozenset({'trap_door', 'secret_trapdoor', 'pit_trap'})
WALL_STYLES = frozenset({'dungeon', 'cave', 'mansion', 'gothic', 'wood', 'office'})
_META_KEYS = frozenset({'name', 'description', 'models', 'version', 'walls', 'wall'})
_WALL_STYLE_ALIASES = {
    'stone': 'dungeon',
    'cellar': 'dungeon',
    'basement': 'dungeon',
    'dungeon': 'dungeon',
    'cave': 'cave',
    'cavern': 'cave',
    'grotto': 'cave',
    'limestone': 'cave',
    'mansion': 'mansion',
    'manor': 'mansion',
    'interior': 'mansion',
    'house': 'mansion',
    'plaster': 'mansion',
    'gothic': 'gothic',
    'gothic_mansion': 'gothic',
    'haunted': 'gothic',
    'victorian': 'gothic',
    'wood': 'wood',
    'timber': 'wood',
    'oak': 'wood',
    'tavern': 'wood',
    'office': 'office',
    'modern': 'office',
    'corporate': 'office',
    'workplace': 'office',
    'startup': 'office',
}
_PALETTE_TO_WALL_STYLE = {
    'interior': 'mansion',
    'mansion': 'mansion',
    'manor': 'mansion',
    'house': 'mansion',
    'dungeon': 'dungeon',
    'cave': 'cave',
    'cavern': 'cave',
    'grotto': 'cave',
    'stone': 'dungeon',
    'cellar': 'dungeon',
    'basement': 'dungeon',
    'wood': 'wood',
    'timber': 'wood',
    'tavern': 'wood',
    'gothic': 'gothic',
    'haunted': 'gothic',
    'office': 'office',
    'modern': 'office',
    'corporate': 'office',
}


def _norm_spec(raw: Any) -> dict | None:
    if isinstance(raw, str) and raw.strip():
        return {'kind': raw.strip().lower()}
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get('kind') or raw.get('model') or '').strip().lower()
    spec = {}
    if kind:
        spec['kind'] = kind
    src = raw.get('src') or raw.get('url') or raw.get('gltf')
    if src:
        spec['src'] = str(src).lstrip('/')
    for key in ('scale', 'y', 'rotate_y'):
        if raw.get(key) is None:
            continue
        try:
            spec[key] = float(raw[key])
        except (TypeError, ValueError):
            pass
    for key in ('open_well', 'wall_attached', 'solid', 'double'):
        if key in raw and raw[key] is not None:
            spec[key] = bool(raw[key])
    return spec or None


def _index_models(data: Any) -> dict[str, dict]:
    if not isinstance(data, dict):
        return {}
    source = data.get('models') if isinstance(data.get('models'), dict) else data
    catalog = {}
    for key, raw in (source or {}).items():
        if key in _META_KEYS:
            continue
        spec = _norm_spec(raw)
        if spec and spec.get('kind'):
            catalog[str(key).strip().lower()] = spec
    return catalog


def _vtt3d_sources(session) -> list[Any]:
    sources = []
    game = getattr(session, 'game_properties', None) or {}
    if isinstance(game.get('vtt3d'), dict):
        sources.append(game.get('vtt3d'))
    root = getattr(session, 'root_path', None)
    if root:
        path = Path(root) / 'vtt3d.yml'
        if path.is_file():
            try:
                data = load_yaml(path, campaign_root=root)
            except Exception:
                data = None
            if isinstance(data, dict):
                sources.append(data)
    return sources


def load_vtt3d_catalog(session) -> dict[str, dict]:
    """Load ``vtt3d.yml`` plus optional ``game.yml`` ``vtt3d`` mapping."""
    catalog = {}
    for data in _vtt3d_sources(session):
        catalog.update(_index_models(data))
    return catalog


def _alias_wall_style(value: Any) -> str | None:
    text = str(value or '').strip().lower()
    if not text:
        return None
    return _WALL_STYLE_ALIASES.get(text, text if text in WALL_STYLES else None)


def _norm_walls(raw: Any) -> dict | None:
    if isinstance(raw, str):
        style = _alias_wall_style(raw)
        return {'style': style} if style else None
    if not isinstance(raw, dict):
        return None
    style = _alias_wall_style(raw.get('style') or raw.get('kind') or raw.get('theme'))
    spec = {}
    if style:
        spec['style'] = style
    src = raw.get('albedo') or raw.get('src') or raw.get('texture') or raw.get('url')
    if src:
        spec['albedo'] = str(src).lstrip('/')
        if 'style' not in spec:
            spec['style'] = 'dungeon'
    return spec or None


def load_vtt3d_walls(session) -> dict:
    """Campaign default wall aesthetic from ``vtt3d.yml`` / ``game.yml``."""
    spec = {'style': 'dungeon'}
    for data in _vtt3d_sources(session):
        walls = _norm_walls(data.get('walls') or data.get('wall'))
        if walls:
            spec = walls
    return spec


def resolve_vtt3d_walls(battle_map, session=None) -> dict:
    """Map YAML ``vtt3d.walls``, then ``render.palette``, then campaign default.

    Styles are generic (``dungeon``, ``cave``, ``mansion``, ``gothic``, ``wood``, ``office``). Campaigns pick
    one; the engine does not hard-code adventure names.
    """
    session = session or getattr(battle_map, 'session', None)
    props = getattr(battle_map, 'properties', None) or {}
    map_props = props.get('map') if isinstance(props.get('map'), dict) else {}
    for block in (props.get('vtt3d'), map_props.get('vtt3d')):
        if isinstance(block, str):
            walls = _norm_walls(block)
        elif isinstance(block, dict):
            walls = _norm_walls(block.get('walls') or block.get('wall') or block)
        else:
            walls = None
        if walls:
            return walls
    palette = None
    render = props.get('render')
    if isinstance(render, dict):
        palette = render.get('palette')
    mapped = _PALETTE_TO_WALL_STYLE.get(str(palette or '').strip().lower())
    if mapped:
        return {'style': mapped}
    return load_vtt3d_walls(session)


def _props_of(obj) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        nested = obj.get('properties')
        if isinstance(nested, dict):
            merged = dict(nested)
            merged.update({k: v for k, v in obj.items() if k != 'properties'})
            return merged
        return obj
    return getattr(obj, 'properties', None) or {}


def _type_and_name(obj) -> tuple[str, str]:
    props = _props_of(obj)
    type_name = str(
        getattr(obj, 'type', None) or props.get('type') or ''
    ).strip().lower()
    name = str(
        getattr(obj, 'name', None) or props.get('name') or props.get('label') or ''
    ).strip().lower()
    return type_name, name


def is_secret_barrier(obj) -> bool:
    """True when this object is a hidden/secret door (generic, not campaign-named)."""
    if obj is None:
        return False
    props = _props_of(obj)
    secret_fn = getattr(obj, 'secret', None)
    if callable(secret_fn):
        try:
            if secret_fn():
                return True
        except Exception:
            pass
    if props.get('secret') or props.get('secret_door'):
        return True
    if props.get('secret_dc') is not None or props.get('secret_perception_dc') is not None:
        return True
    type_name, name = _type_and_name(obj)
    return 'secret_door' in type_name or 'secret_door' in name


def infer_hatch_kind(obj) -> str | None:
    """Floor hatches: trapdoors, secret trapdoors, pit traps."""
    type_name, name = _type_and_name(obj)
    blob = f'{type_name} {name}'
    if type_name == 'pit_trap' or 'pit_trap' in blob or 'pit trap' in blob:
        return 'pit_trap'
    if 'trap_door' in blob or 'trapdoor' in blob:
        if is_secret_barrier(obj):
            return 'secret_trapdoor'
        return 'trap_door'
    return None


def infer_door_kind(obj) -> str:
    if infer_hatch_kind(obj):
        return 'skip'
    type_name, name = _type_and_name(obj)
    class_name = ''
    if obj is not None and not isinstance(obj, dict):
        class_name = obj.__class__.__name__
    if (
        class_name == 'WindowObjectWall'
        or type_name.startswith('window_')
        or type_name.startswith('corner_window')
    ):
        return 'window'
    if is_secret_barrier(obj):
        return 'secret_door'
    blob = f'{type_name} {name}'
    if 'portcullis' in blob:
        return 'portcullis'
    return 'door'


def lookup_catalog(obj, catalog: dict | None) -> dict | None:
    if not catalog:
        return None
    type_name, name = _type_and_name(obj)
    for key in (type_name, name):
        if key and key in catalog:
            return dict(catalog[key])
    return None


def resolve_vtt3d_model(obj, catalog: dict | None = None, *, role: str = 'object') -> dict | None:
    """Return ``{kind, src?, scale?, y?}`` or None."""
    props = _props_of(obj)
    inline = _norm_spec(props.get('vtt3d') if isinstance(obj, dict) else None)
    if inline is None and not isinstance(obj, dict):
        inline = _norm_spec(props.get('vtt3d'))
    if inline is None and isinstance(obj, dict):
        inline = _norm_spec(obj.get('vtt3d'))
    if inline and inline.get('kind'):
        return inline
    found = lookup_catalog(obj, catalog)
    hatch = infer_hatch_kind(obj)
    if found:
        if hatch == 'secret_trapdoor' and found.get('kind') == 'trap_door':
            found = dict(found)
            found['kind'] = 'secret_trapdoor'
        base = found
    elif hatch:
        base = {'kind': hatch}
    elif role == 'door':
        base = {'kind': infer_door_kind(obj)}
    else:
        base = None
    if inline and base:
        merged = dict(base)
        merged.update(inline)
        return merged
    return inline or base
