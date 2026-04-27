"""Phase 4 effect serialization registry.

Many spell effect classes already define ``to_dict`` / ``from_dict`` (Bless,
Bane, Mage Armor, Resistance, Guidance, Persistent Zones, …) but the
top-level save/load code has no uniform way to round-trip them. This
registry provides a single dispatcher::

    from natural20.utils.effect_registry import (
        register_effect, serialize_effect, deserialize_effect,
        serialize_effects_dict, deserialize_effects_dict,
    )

    @register_effect('bless')
    class BlessSpell: ...

The registry is opt-in: nothing in the engine forces effects to register.
It exists so save/load callers (and tests) can serialize a heterogeneous
``Entity.effects`` mapping by looking up each entry's class and calling
its ``to_dict`` / ``from_dict``.
"""

from __future__ import annotations


_EFFECT_REGISTRY: dict = {}


def register_effect(effect_id, cls=None):
    """Decorator or direct call to register an effect class."""
    def _register(klass):
        _EFFECT_REGISTRY[str(effect_id)] = klass
        # Stash the id back on the class so we can look it up on serialize.
        try:
            setattr(klass, '_effect_registry_id', str(effect_id))
        except Exception:
            pass
        return klass
    if cls is not None:
        return _register(cls)
    return _register


def lookup_effect(effect_id):
    return _EFFECT_REGISTRY.get(str(effect_id))


def registered_effects():
    return sorted(_EFFECT_REGISTRY.keys())


def effect_id_for(obj) -> str | None:
    """Return the registry id for an effect instance, or None."""
    eid = getattr(obj, '_effect_registry_id', None)
    if eid is not None:
        return str(eid)
    # Fall back to class id attribute used by some spells (e.g. ``id``).
    eid = getattr(getattr(obj, '__class__', None), '_effect_registry_id', None)
    if eid is not None:
        return str(eid)
    eid = getattr(obj, 'id', None)
    if eid is not None and lookup_effect(eid) is not None:
        return str(eid)
    return None


def serialize_effect(obj) -> dict | None:
    """Serialize an effect instance via its ``to_dict``.

    Returns ``{'effect_id': ..., 'data': {...}}`` or ``None`` if the
    effect is not registered or has no ``to_dict``.
    """
    eid = effect_id_for(obj)
    if eid is None:
        return None
    to_dict = getattr(obj, 'to_dict', None)
    if not callable(to_dict):
        return None
    try:
        data = to_dict()
    except Exception:
        return None
    return {'effect_id': eid, 'data': data}


def deserialize_effect(payload, *, session=None):
    """Re-instantiate an effect from a payload built by ``serialize_effect``."""
    if not isinstance(payload, dict):
        return None
    cls = lookup_effect(payload.get('effect_id'))
    if cls is None:
        return None
    from_dict = getattr(cls, 'from_dict', None)
    if not callable(from_dict):
        return None
    data = payload.get('data') or {}
    # Inject session if it isn't already in the payload but the class
    # signature accepts it (best-effort, swallow errors).
    try:
        if 'session' not in data and session is not None:
            try:
                return from_dict({**data, 'session': session})
            except Exception:
                pass
        return from_dict(data)
    except Exception:
        return None


def serialize_effects_dict(effects: dict) -> dict:
    """Serialize an ``Entity.effects``-shaped mapping.

    Effects whose class isn't registered are skipped (the caller can keep
    its existing ad-hoc serialization for those).
    """
    out = {}
    for kind, descriptors in (effects or {}).items():
        kind_out = []
        for descriptor in descriptors:
            if not isinstance(descriptor, dict):
                continue
            payload = serialize_effect(descriptor.get('effect'))
            if payload is None:
                continue
            new_desc = {k: v for k, v in descriptor.items() if k != 'effect'}
            new_desc['effect'] = payload
            # Source is typically an Entity; persist by uid.
            src = descriptor.get('source')
            if src is not None and hasattr(src, 'entity_uid'):
                new_desc['source'] = str(src.entity_uid)
            kind_out.append(new_desc)
        if kind_out:
            out[kind] = kind_out
    return out


def deserialize_effects_dict(serialized: dict, *, session=None) -> dict:
    """Inverse of ``serialize_effects_dict``."""
    out = {}
    for kind, descriptors in (serialized or {}).items():
        kind_out = []
        for descriptor in descriptors:
            if not isinstance(descriptor, dict):
                continue
            new_desc = dict(descriptor)
            payload = new_desc.get('effect')
            if isinstance(payload, dict) and 'effect_id' in payload:
                new_desc['effect'] = deserialize_effect(payload, session=session)
            src = new_desc.get('source')
            if isinstance(src, str) and session is not None:
                registry = getattr(session, 'entity_registry', None)
                if registry is not None:
                    new_desc['source'] = registry.get(src) or src
            kind_out.append(new_desc)
        out[kind] = kind_out
    return out
