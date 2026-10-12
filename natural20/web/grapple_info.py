"""Grapple relationship summaries for map rendering (2D tiles, tooltips, 3D state)."""

from __future__ import annotations

from typing import Any, Dict, List


def _ref(other) -> Dict[str, Any] | None:
    uid = getattr(other, 'entity_uid', None)
    if not uid:
        return None
    try:
        name = other.label()
    except Exception:
        name = getattr(other, 'name', None) or uid
    return {'id': uid, 'name': str(name)}


def _unique_refs(entities) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    seen = set()
    for other in entities or []:
        ref = _ref(other)
        if ref is None or ref['id'] in seen:
            continue
        seen.add(ref['id'])
        refs.append(ref)
    return refs


def grapple_info(entity) -> Dict[str, Any]:
    """Return who grapples ``entity`` and whom ``entity`` grapples.

    ``grappled_by`` entries carry ``escape_dc`` when the grapple was applied
    with a fixed escape DC (e.g. monster ``grapple_instead`` attacks).
    """
    grappled_by = _unique_refs(getattr(entity, 'grapples', None))
    grappling_fn = getattr(entity, 'grappling_targets', None)
    grappling_src = grappling_fn() if callable(grappling_fn) else getattr(entity, 'grappling', None)
    grappling = _unique_refs(grappling_src)

    attrs = getattr(entity, 'attributes', None)
    escape_dcs = attrs.get('grapple_escape_dcs') if isinstance(attrs, dict) else None
    if isinstance(escape_dcs, dict):
        for ref in grappled_by:
            dc = escape_dcs.get(ref['id'])
            if dc is not None:
                ref['escape_dc'] = dc

    grappled_fn = getattr(entity, 'grappled', None)
    grappled = bool(grappled_fn()) if callable(grappled_fn) else bool(grappled_by)
    return {
        'grappled': grappled or bool(grappled_by),
        'grappled_by': grappled_by,
        'grappling': grappling,
    }


def grapple_tooltip_lines(info: Dict[str, Any]) -> List[str]:
    """Plain-text lines describing a grapple summary from :func:`grapple_info`."""
    lines: List[str] = []
    for ref in info.get('grappled_by') or []:
        line = f"Grappled by {ref['name']}"
        if ref.get('escape_dc') is not None:
            line += f" (escape DC {ref['escape_dc']})"
        lines.append(line)
    if info.get('grappled') and not info.get('grappled_by'):
        lines.append("Grappled")
    for ref in info.get('grappling') or []:
        lines.append(f"Grappling {ref['name']}")
    return lines


def grapple_tile_attributes(entity) -> Dict[str, Any]:
    """Tile dict keys for a token tile; empty when no grapple is involved."""
    info = grapple_info(entity)
    if not (info['grappled'] or info['grappled_by'] or info['grappling']):
        return {}
    return {
        'grappled': info['grappled'],
        'grappled_by': info['grappled_by'],
        'grappling': info['grappling'],
        'grapple_tooltip': "\n".join(grapple_tooltip_lines(info)),
    }
