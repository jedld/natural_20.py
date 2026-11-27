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


# ---------------------------------------------------------------------------
# entity token models (``vtt3d.yml`` -> ``tokens:``)
# ---------------------------------------------------------------------------

#: preferred entry-file order when a token ``src`` names a directory
TOKEN_ENTRY_EXTS = ('.glb', '.gltf', '.obj', '.stl')


def _norm_token_spec(raw: Any) -> dict | None:
    """Normalize one ``tokens:`` entry into a client-facing model spec."""
    if isinstance(raw, str) and raw.strip():
        raw = {'src': raw}
    if not isinstance(raw, dict):
        return None
    spec: dict = {}
    src = raw.get('src') or raw.get('model') or raw.get('url') or raw.get('gltf')
    if src:
        src = str(src).strip().lstrip('/')
        if src.startswith('assets/'):
            src = src[len('assets/'):]
        if src:
            spec['src'] = src
    for key in ('scale', 'y', 'height', 'rotate_y'):
        if raw.get(key) is None:
            continue
        try:
            spec[key] = float(raw[key])
        except (TypeError, ValueError):
            pass
    color = raw.get('color') or raw.get('tint')
    if color:
        spec['color'] = str(color).strip()
    label = raw.get('label') or raw.get('name')
    if label:
        spec['label'] = str(label).strip()
    if raw.get('library') is not None:
        spec['library'] = bool(raw['library'])
    return spec or None


def load_vtt3d_tokens(session) -> dict[str, dict]:
    """Campaign token-model assignments keyed by entity uid / NPC type / name.

    Keys are matched case-insensitively by :func:`resolve_token_model`.
    """
    tokens: dict[str, dict] = {}
    for data in _vtt3d_sources(session):
        block = data.get('tokens')
        if not isinstance(block, dict):
            continue
        for key, raw in block.items():
            spec = _norm_token_spec(raw)
            if spec:
                tokens[str(key).strip()] = spec
    return tokens


def entity_token_keys(entity) -> list[str]:
    """Candidate lookup keys for an entity, highest priority first."""
    keys: list[str] = []
    if entity is None:
        return keys
    uid = getattr(entity, 'entity_uid', None) or _props_of(entity).get('entity_uid') or _props_of(entity).get('uid')
    if uid:
        keys.append(str(uid).strip())
    npc_type = getattr(entity, 'npc_type', None) or _props_of(entity).get('id')
    if npc_type:
        keys.append(str(npc_type).strip())
    name = getattr(entity, 'name', None) or _props_of(entity).get('name')
    if name:
        keys.append(str(name).strip())
        # spawned NPC copies are named "Type #3"; also try the bare base name
        base = keys[-1].rsplit('#', 1)[0].strip()
        if base and base not in keys:
            keys.append(base)
    return keys


#: size categories in ascending order (5e)
_SIZE_ORDER = ('tiny', 'small', 'medium', 'large', 'huge', 'gargantuan')


def natural_size_category(entity) -> str | None:
    """The entity's base size category, ignoring active ``size_override``
    effects (Enlarge/Reduce, Goliath Large Form, ...) — the size a token
    model was authored at."""
    if entity is None:
        return None
    size = _props_of(entity).get('size')
    if size:
        return str(size).strip().lower()
    race_props = getattr(entity, 'race_properties', None) or {}
    if race_props.get('size'):
        return str(race_props['size']).strip().lower()
    return None


def model_size_scale(entity) -> float | None:
    """Linear scale multiplier for a token model when the entity's *current*
    size differs from the size it was authored at.

    ``entity.size()`` already honors registered ``size_override`` effects
    (Enlarge/Reduce, Large Form, ...); comparing it against the base size
    yields the visual scale. 5e size changes double/halve linear dimensions
    per category step, so one Enlarge on a Medium creature is ``2.0``.
    Returns None when unchanged or not comparable.
    """
    if entity is None:
        return None
    natural = natural_size_category(entity)
    current = None
    size_fn = getattr(entity, 'size', None)
    if callable(size_fn):
        try:
            current = str(size_fn() or '').strip().lower() or None
        except Exception:
            current = None
    if not current:
        current = natural
    if not current or not natural or current == natural:
        return None
    if current not in _SIZE_ORDER or natural not in _SIZE_ORDER:
        return None
    return float(2 ** (_SIZE_ORDER.index(current) - _SIZE_ORDER.index(natural)))


def resolve_token_model(entity, tokens: dict | None) -> dict | None:
    """Match an entity against the campaign ``tokens:`` catalog."""
    if not tokens:
        return None
    lowered = {str(k).strip().lower(): v for k, v in tokens.items()}
    for key in entity_token_keys(entity):
        spec = lowered.get(key.lower())
        if spec:
            return dict(spec)
    return None


def resolve_token_src(root: Any, src: str | None) -> str | None:
    """Resolve a token ``src`` (file or directory) to a serveable asset path.

    Directory sources pick their entry file by extension preference
    (``glb`` > ``gltf`` > ``obj`` > ``stl``). Returns the path relative to
    ``<campaign>/assets`` or None when nothing exists on disk.
    """
    if not src or root is None:
        return None
    src = str(src).strip().lstrip('/')
    if src.startswith('assets/'):
        src = src[len('assets/'):]
    assets_root = Path(root) / 'assets'
    target = (assets_root / src)
    try:
        target = target.resolve()
        if not str(target).startswith(str(assets_root.resolve())):
            return None
    except Exception:
        return None
    if target.is_file():
        return src
    if target.is_dir():
        name = target.name
        for ext in TOKEN_ENTRY_EXTS:
            candidate = target / f'{name}{ext}'
            if candidate.is_file():
                return f'{src}/{candidate.name}'
        for ext in TOKEN_ENTRY_EXTS:
            try:
                matches = sorted(target.glob(f'*{ext}'))
            except Exception:
                matches = []
            if matches:
                return f'{src}/{matches[0].name}'
    for ext in TOKEN_ENTRY_EXTS:
        if (assets_root / f'{src}{ext}').is_file():
            return f'{src}{ext}'
    return None
