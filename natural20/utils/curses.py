"""Curse helpers shared by Remove Curse (and any future curse-breaking feature).

A *curse* is any effect whose spell YAML sets ``curse: true`` (e.g. Hex), an
effect object with a truthy ``curse`` attribute, or the generic ``cursed``
status. Magic items flagged ``cursed: true`` in item YAML keep their curse
mechanics, but once a curse-breaking spell touches the bearer the item is
listed in ``properties['curse_broken_items']`` and the bearer's attunement to
it ends (``natural20/utils/attunement.py``), so it can be removed.
"""
from __future__ import annotations

from typing import Iterable, List


def is_curse_effect(effect) -> bool:
    if effect is None or isinstance(effect, str):
        return False
    if getattr(effect, 'curse', False) is True:
        return True
    for attr in ('properties', 'spell_properties'):
        props = getattr(effect, attr, None)
        if isinstance(props, dict) and props.get('curse'):
            return True
    return False


def _descriptor_effects(entity) -> Iterable:
    for descriptors in (getattr(entity, 'effects', None) or {}).values():
        for descriptor in descriptors or []:
            if isinstance(descriptor, dict):
                yield descriptor.get('effect')
    for descriptors in (getattr(entity, 'entity_event_hooks', None) or {}).values():
        for descriptor in descriptors or []:
            if isinstance(descriptor, dict):
                yield descriptor.get('effect')


def curse_effects_on(entity) -> List:
    """Distinct curse effects currently affecting ``entity``."""
    found, seen = [], set()
    for effect in _descriptor_effects(entity):
        if is_curse_effect(effect) and id(effect) not in seen:
            seen.add(id(effect))
            found.append(effect)
    return found


def cursed_items_of(entity, session=None) -> List[str]:
    """Names of equipped items whose YAML sets ``cursed: true``."""
    session = session or getattr(entity, 'session', None)
    if session is None:
        return []
    names = []
    for name in (getattr(entity, 'properties', None) or {}).get('equipped', []) or []:
        try:
            item = session.load_thing(name)
        except Exception:
            item = None
        if isinstance(item, dict) and item.get('cursed'):
            names.append(name)
    return names


def has_curse(entity, session=None) -> bool:
    if entity is None:
        return False
    if 'cursed' in (getattr(entity, 'statuses', None) or []):
        return True
    if curse_effects_on(entity):
        return True
    broken = set((getattr(entity, 'properties', None) or {}).get('curse_broken_items', []) or [])
    return any(name not in broken for name in cursed_items_of(entity, session))


def end_curse_effect(entity, effect) -> None:
    """End one curse on ``entity``: the caster dismisses it (dropping
    concentration and its casted-effect bookkeeping), then any leftover
    registrations on ``entity`` are removed."""
    source = getattr(effect, 'source', None)
    if source is not None and not isinstance(source, str) and hasattr(source, 'dismiss_effect'):
        source.dismiss_effect(effect)
    if hasattr(entity, 'remove_effect'):
        entity.remove_effect(effect)
    for key in ('effects', 'entity_event_hooks'):
        table = getattr(entity, key, None)
        if isinstance(table, dict):
            setattr(entity, key, {
                k: [d for d in v if not (isinstance(d, dict) and d.get('effect') is effect)]
                for k, v in table.items()
            })


def break_curses(entity, session=None) -> dict:
    """End every curse on ``entity``. Returns a summary of what was removed."""
    ended = []
    for effect in curse_effects_on(entity):
        label = effect.label() if hasattr(effect, 'label') else str(effect)
        end_curse_effect(entity, effect)
        ended.append(label)

    status_cleared = False
    statuses = getattr(entity, 'statuses', None)
    if isinstance(statuses, list):
        while 'cursed' in statuses:
            statuses.remove('cursed')
            status_cleared = True

    items = cursed_items_of(entity, session)
    if items:
        broken = list(entity.properties.get('curse_broken_items', []) or [])
        for name in items:
            if name not in broken:
                broken.append(name)
        entity.properties['curse_broken_items'] = broken
        from natural20.utils.attunement import attuned_items, ensure_tracking, request_end
        for name in items:
            if name in attuned_items(entity):
                ensure_tracking(entity)
                request_end(entity, name, force=True)

    return {'effects': ended, 'status_cleared': status_cleared, 'items': items}
