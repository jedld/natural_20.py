"""Magic item attunement (DMG 2014 p.136 and DMG 2024 ch.7 — the rules match).

* Attuning takes a short rest focused on only that item while in physical
  contact with it. Voluntarily ending attunement takes another such rest and
  is impossible while the item's curse holds.
* A creature can be attuned to at most ``Ruleset.attunement_limit()`` items
  (3). Class YAML ``attunement`` entries raise it (Artificer Magic Item
  Adept/Savant/Master) and can waive item prerequisites::

      attunement:
        - feature: magic_item_adept
          max: 4
        - feature: magic_item_savant
          max: 5
          ignore_prerequisites: true

* Only one copy of an item can be attuned (attunement is keyed by item key).
* Attunement ends when the creature dies, or once the item has been out of
  its possession for 24 hours of campaign time.

Item YAML prerequisites: ``attunement_class`` / ``attunement_race`` /
``attunement_alignment`` (string or list) and ``attunement_spellcaster: true``.

Sheet state (``entity.properties``):

* ``attuned`` — list of item keys. When absent the sheet is *untracked*: every
  attunement item counts as attuned (legacy behaviour). The first managed
  change seeds the list from the equipped attunement items.
* ``attunement_pending`` — ``[{item, mode: attune|end}]`` completed by the next
  rests, ``Ruleset.attunements_per_rest`` changes per rest.
* ``attunement_separated`` — ``{item: game_time}`` when the item left the
  creature's possession.
* ``attunement_limit`` — optional per-sheet override of the limit.
"""

from __future__ import annotations

from natural20.utils.item_mechanics import is_attuned

SEPARATION_SECONDS = 24 * 3600
DEFAULT_LIMIT = 3


class AttunementError(ValueError):
    """An attunement request the rules do not allow (message is user-facing)."""


def _props(entity):
    props = getattr(entity, 'properties', None)
    return props if isinstance(props, dict) else None


def _ruleset(entity):
    return getattr(getattr(entity, 'session', None), 'ruleset', None)


def _load(entity, key):
    session = getattr(entity, 'session', None)
    if session is None or not key:
        return None
    try:
        item = session.load_thing(key)
    except Exception:
        return None
    return item if isinstance(item, dict) else None


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _norm(value):
    return str(value or '').strip().lower().replace(' ', '_').replace('-', '_')


def item_label(entity, key):
    item = _load(entity, key) or {}
    return str(item.get('label') or item.get('name') or key).replace('_', ' ')


def requires_attunement(entity, key, item=None):
    item = item if item is not None else _load(entity, key)
    return bool((item or {}).get('requires_attunement'))


def tracking_enabled(entity):
    return isinstance((_props(entity) or {}).get('attuned'), list)


def _class_specs(entity):
    try:
        from natural20.utils.class_mechanics import class_specs
        return class_specs(entity, 'attunement')
    except Exception:
        return []


def attunement_limit(entity):
    props = _props(entity) or {}
    if props.get('attunement_limit') is not None:
        try:
            return max(0, int(props['attunement_limit']))
        except (TypeError, ValueError):
            pass
    ruleset = _ruleset(entity)
    limit = ruleset.attunement_limit() if ruleset is not None else DEFAULT_LIMIT
    from natural20.utils.class_mechanics import spec_value
    for klass, spec in _class_specs(entity):
        if spec.get('max') is not None:
            limit = max(limit, spec_value(entity, spec, klass, key='max'))
    return int(limit)


def ignores_prerequisites(entity):
    return any(spec.get('ignore_prerequisites') for _k, spec in _class_specs(entity))


def requires_rest(entity):
    ruleset = _ruleset(entity)
    return ruleset.attunement_requires_rest() if ruleset is not None else True


def changes_per_rest(entity, rest_kind):
    ruleset = _ruleset(entity)
    if ruleset is not None:
        return max(0, int(ruleset.attunements_per_rest(rest_kind)))
    return 2 if rest_kind == 'long_rest' else 1


def possesses(entity, key):
    """In physical contact: equipped, carried, or inside a carried container."""
    props = _props(entity) or {}
    if str(key) in [str(k) for k in props.get('equipped') or []]:
        return True
    try:
        return int(entity.item_count(key) or 0) > 0
    except Exception:
        return str(key) in (getattr(entity, 'inventory', None) or {})


def _equipped_attunement_items(entity):
    out = []
    for key in (_props(entity) or {}).get('equipped') or []:
        key = str(key)
        if key not in out and requires_attunement(entity, key):
            out.append(key)
    return out


def attuned_items(entity):
    """Item keys the creature is attuned to (untracked sheets: equipped attunement items)."""
    props = _props(entity) or {}
    if tracking_enabled(entity):
        return [str(k) for k in props['attuned']]
    return _equipped_attunement_items(entity)[:attunement_limit(entity)]


def pending_changes(entity):
    pending = (_props(entity) or {}).get('attunement_pending') or []
    return [dict(p) for p in pending if isinstance(p, dict) and p.get('item')]


def ensure_tracking(entity):
    """Start tracking, keeping what already worked on an untracked sheet."""
    props = _props(entity)
    if props is None or tracking_enabled(entity):
        return
    props['attuned'] = attuned_items(entity)


def _invalidate(entity):
    getattr(entity, '__dict__', {}).pop('_item_mechanics_cache', None)


def _set_attuned(entity, keys):
    _props(entity)['attuned'] = list(keys)
    _invalidate(entity)


def _set_pending(entity, pending):
    props = _props(entity)
    if pending:
        props['attunement_pending'] = pending
    else:
        props.pop('attunement_pending', None)


def is_cursed(entity, key, item=None):
    item = item if item is not None else _load(entity, key)
    if not (item or {}).get('cursed'):
        return False
    broken = _as_list((_props(entity) or {}).get('curse_broken_items'))
    return str(key) not in broken


def _creature_classes(entity):
    classes = []
    try:
        c_class = entity.c_class()
    except Exception:
        c_class = None
    if isinstance(c_class, dict):
        classes.extend(_norm(k) for k in c_class)
    elif c_class:
        classes.append(_norm(c_class))
    return classes


def _creature_races(entity):
    props = _props(entity) or {}
    races = [_norm(r) for r in _as_list(props.get('race'))]
    for key in ('subrace', 'species'):
        races.extend(_norm(r) for r in _as_list(props.get(key)))
    return [r for r in races if r]


def _is_spellcaster(entity):
    """2014 errata: can cast at least one spell from its own traits or features."""
    try:
        return bool(entity.prepared_spells())
    except Exception:
        return False


def prerequisite_issue(entity, item):
    """Why ``entity`` fails the item's attunement prerequisites (``None`` = ok)."""
    item = item or {}
    if ignores_prerequisites(entity):
        return None
    classes = [_norm(c) for c in _as_list(item.get('attunement_class'))]
    if classes and not set(classes) & set(_creature_classes(entity)):
        return f"Requires attunement by a {' or '.join(c.replace('_', ' ') for c in classes)}."
    races = [_norm(r) for r in _as_list(item.get('attunement_race'))]
    if races:
        mine = _creature_races(entity)
        if not any(r == m or r in m.split('_') for r in races for m in mine):
            return f"Requires attunement by a {' or '.join(r.replace('_', ' ') for r in races)}."
    alignments = [_norm(a) for a in _as_list(item.get('attunement_alignment'))]
    if alignments:
        mine = _norm(entity.alignment() if hasattr(entity, 'alignment') else '')
        if not any(a == mine or a in mine.split('_') for a in alignments):
            return f"Requires a {' or '.join(a.replace('_', ' ') for a in alignments)} creature."
    if item.get('attunement_spellcaster') and not _is_spellcaster(entity):
        return 'Requires attunement by a spellcaster.'
    return None


def attune_issue(entity, key, force=False, pending_ok=True):
    """Why ``entity`` cannot attune to ``key`` now (``None`` = allowed).

    ``force`` (DM) waives prerequisites; the item must still be held and the
    limit still applies."""
    key = str(key)
    item = _load(entity, key)
    if item is None:
        return 'Unknown item.'
    if not item.get('requires_attunement'):
        return f"{item_label(entity, key)} doesn't require attunement."
    if not possesses(entity, key):
        return f"You must be holding or carrying {item_label(entity, key)} to attune to it."
    attuned = attuned_items(entity)
    if key in attuned:
        return f"Already attuned to {item_label(entity, key)}."
    pending = pending_changes(entity) if pending_ok else []
    if any(p['item'] == key and p.get('mode') == 'attune' for p in pending):
        return f"Attunement to {item_label(entity, key)} is already pending."
    if not force:
        issue = prerequisite_issue(entity, item)
        if issue:
            return issue
    used = len(attuned)
    used += sum(1 for p in pending if p.get('mode') == 'attune')
    used -= sum(1 for p in pending if p.get('mode') == 'end' and p['item'] in attuned)
    if used >= attunement_limit(entity):
        return (f"You can be attuned to at most {attunement_limit(entity)} magic items. "
                "End an attunement first.")
    return None


def end_issue(entity, key, force=False):
    key = str(key)
    if key not in attuned_items(entity):
        return f"Not attuned to {item_label(entity, key)}."
    if any(p['item'] == key and p.get('mode') == 'end' for p in pending_changes(entity)):
        return f"Ending attunement to {item_label(entity, key)} is already pending."
    if not force and is_cursed(entity, key):
        return f"{item_label(entity, key)} is cursed; the bond can't be broken voluntarily."
    return None


def _emit(entity, outcome, key, reason=None, **extra):
    session = getattr(entity, 'session', None)
    manager = getattr(session, 'event_manager', None)
    if manager is None:
        return
    event = {'event': 'attunement', 'source': entity, 'item': key,
             'item_label': item_label(entity, key), 'outcome': outcome}
    if reason:
        event['reason'] = reason
    event.update(extra)
    try:
        manager.received_event(event)
    except Exception:
        pass


def _attune_now(entity, key):
    attuned = attuned_items(entity)
    if key not in attuned:
        attuned.append(key)
    _set_attuned(entity, attuned)
    separated = (_props(entity) or {}).get('attunement_separated')
    if isinstance(separated, dict):
        separated.pop(key, None)
    _emit(entity, 'attuned', key)


def _end_now(entity, key, outcome='ended', reason=None):
    _set_attuned(entity, [k for k in attuned_items(entity) if k != key])
    separated = (_props(entity) or {}).get('attunement_separated')
    if isinstance(separated, dict):
        separated.pop(key, None)
        if not separated:
            _props(entity).pop('attunement_separated', None)
    _emit(entity, outcome, key, reason=reason)


def _in_combat(entity, battle):
    if battle is None:
        return False
    try:
        return bool(battle.ongoing()) and entity in battle.entities
    except Exception:
        return False


def request_attunement(entity, key, battle=None, force=False):
    """Attune now (DM ``force`` or no-rest house rule) or queue for the next rest.

    Returns ``{'status': 'attuned'|'pending', 'item': key}``."""
    key = str(key)
    issue = attune_issue(entity, key, force=force)
    if issue:
        raise AttunementError(issue)
    ensure_tracking(entity)
    if force or (not requires_rest(entity) and not _in_combat(entity, battle)):
        _attune_now(entity, key)
        return {'status': 'attuned', 'item': key}
    pending = [p for p in pending_changes(entity) if p['item'] != key]
    pending.append({'item': key, 'mode': 'attune'})
    _set_pending(entity, pending)
    _emit(entity, 'pending', key, mode='attune')
    return {'status': 'pending', 'item': key}


def request_end(entity, key, battle=None, force=False):
    """End attunement now (DM ``force`` or no-rest house rule) or at the next rest."""
    key = str(key)
    issue = end_issue(entity, key, force=force)
    if issue:
        raise AttunementError(issue)
    ensure_tracking(entity)
    if force or (not requires_rest(entity) and not _in_combat(entity, battle)):
        _end_now(entity, key)
        _set_pending(entity, [p for p in pending_changes(entity) if p['item'] != key])
        return {'status': 'ended', 'item': key}
    pending = [p for p in pending_changes(entity) if p['item'] != key]
    pending.append({'item': key, 'mode': 'end'})
    _set_pending(entity, pending)
    _emit(entity, 'pending', key, mode='end')
    return {'status': 'pending', 'item': key}


def cancel_pending(entity, key):
    key = str(key)
    pending = pending_changes(entity)
    remaining = [p for p in pending if p['item'] != key]
    if len(remaining) == len(pending):
        raise AttunementError(f"Nothing pending for {item_label(entity, key)}.")
    _set_pending(entity, remaining)
    return {'status': 'cancelled', 'item': key}


def complete_pending(entity, rest_kind):
    """Finish queued changes at the end of a rest (one focused hour each).

    Endings go first so a swap (end one, attune another) fits the limit.
    Returns ``[{item, mode, status, reason?}]``."""
    pending = pending_changes(entity)
    if not pending:
        return []
    allowance = changes_per_rest(entity, rest_kind)
    ordered = sorted(pending, key=lambda p: 0 if p.get('mode') == 'end' else 1)
    results, remaining = [], []
    for change in ordered:
        if allowance <= 0:
            remaining.append(change)
            continue
        allowance -= 1
        key, mode = change['item'], change.get('mode') or 'attune'
        if mode == 'end':
            issue = None if key in attuned_items(entity) else 'not attuned'
            if issue is None and is_cursed(entity, key):
                issue = 'the item is cursed'
            if issue is None:
                _end_now(entity, key)
                results.append({'item': key, 'mode': mode, 'status': 'ended'})
                continue
        else:
            issue = attune_issue(entity, key, pending_ok=False)
            if issue is None:
                _attune_now(entity, key)
                results.append({'item': key, 'mode': mode, 'status': 'attuned'})
                continue
        _emit(entity, 'failed', key, reason=issue, mode=mode)
        results.append({'item': key, 'mode': mode, 'status': 'failed', 'reason': issue})
    order = {id(p): i for i, p in enumerate(pending)}
    remaining.sort(key=lambda p: order.get(id(p), 0))
    _set_pending(entity, remaining)
    return results


def end_all(entity, reason='died'):
    """Death ends every attunement (and drops queued changes)."""
    props = _props(entity)
    if props is None:
        return []
    props.pop('attunement_pending', None)
    if not tracking_enabled(entity):
        return []
    ended = attuned_items(entity)
    for key in ended:
        _end_now(entity, key, outcome='lost', reason=reason)
    return ended


def check_separation(entity, game_time):
    """End attunement to items out of the creature's possession for 24 hours."""
    props = _props(entity)
    if props is None or not tracking_enabled(entity) or not props['attuned']:
        if props is not None:
            props.pop('attunement_separated', None)
        return []
    separated = props.get('attunement_separated')
    separated = dict(separated) if isinstance(separated, dict) else {}
    ended = []
    game_time = int(game_time or 0)
    for key in attuned_items(entity):
        if possesses(entity, key):
            separated.pop(key, None)
            continue
        since = separated.setdefault(key, game_time)
        if game_time - int(since) >= SEPARATION_SECONDS:
            separated.pop(key, None)
            props['attunement_separated'] = separated
            _end_now(entity, key, outcome='lost', reason='separated')
            separated = dict(props.get('attunement_separated') or {})
            ended.append(key)
    if separated:
        props['attunement_separated'] = separated
    else:
        props.pop('attunement_separated', None)
    return ended


def tick_attunement(session):
    """Called whenever the campaign clock advances."""
    registry = getattr(session, 'entity_registry', None)
    entities = getattr(registry, '_uid_to_entity', None)
    if not entities:
        return
    game_time = int(getattr(session, 'game_time', 0) or 0)
    for entity in list(entities.values()):
        props = _props(entity)
        if props and isinstance(props.get('attuned'), list) and props['attuned']:
            check_separation(entity, game_time)


def _candidate_keys(entity):
    keys = []
    for key in (_props(entity) or {}).get('equipped') or []:
        if str(key) not in keys:
            keys.append(str(key))
    for key in (getattr(entity, 'inventory', None) or {}):
        if str(key) not in keys:
            keys.append(str(key))
    if hasattr(entity, 'iter_nested_inventory'):
        try:
            for _container, content in entity.iter_nested_inventory():
                key = content.get('type') or content.get('item')
                if key and str(key) not in keys:
                    keys.append(str(key))
        except Exception:
            pass
    return keys


def attunement_row(entity, key, force=False):
    """Display state of one attunement item (``None`` if it needs no attunement)."""
    key = str(key)
    item = _load(entity, key)
    if not item or not item.get('requires_attunement'):
        return None
    is_on = key in attuned_items(entity)
    pending = next((p.get('mode') or 'attune' for p in pending_changes(entity) if p['item'] == key), None)
    equipped = [str(k) for k in (_props(entity) or {}).get('equipped') or []]
    row = {
        'item': key,
        'label': item_label(entity, key),
        'icon': item.get('icon') or f"/assets/items/{item.get('image', key)}.png",
        'attuned': is_on,
        'tracked': tracking_enabled(entity),
        'equipped': key in equipped,
        'held': possesses(entity, key),
        'cursed': is_cursed(entity, key, item),
        'pending': pending,
        'prerequisite': prerequisite_issue(entity, item),
        'requires_rest': requires_rest(entity),
        'issue': None,
    }
    if not pending:
        row['issue'] = end_issue(entity, key, force=force) if is_on else attune_issue(entity, key, force=force)
    return row


def attunement_status(entity, force=False):
    """Display model for the character sheet."""
    attuned = attuned_items(entity)
    pending = pending_changes(entity)
    keys = _candidate_keys(entity)
    keys += [k for k in attuned if k not in keys]
    rows = [row for row in (attunement_row(entity, key, force=force) for key in keys) if row]
    rows.sort(key=lambda r: (not r['attuned'], r['label'].lower()))
    separated = (_props(entity) or {}).get('attunement_separated') or {}
    return {
        'tracked': tracking_enabled(entity),
        'limit': attunement_limit(entity),
        'count': len(attuned),
        'requires_rest': requires_rest(entity),
        'per_short_rest': changes_per_rest(entity, 'short_rest'),
        'per_long_rest': changes_per_rest(entity, 'long_rest'),
        'items': rows,
        'pending': pending,
        'separated': dict(separated) if isinstance(separated, dict) else {},
    }


__all__ = [
    'AttunementError', 'attune_issue', 'attuned_items', 'attunement_limit',
    'attunement_row', 'attunement_status', 'cancel_pending', 'check_separation', 'complete_pending',
    'end_all', 'end_issue', 'ensure_tracking', 'is_attuned', 'pending_changes',
    'possesses', 'prerequisite_issue', 'request_attunement', 'request_end',
    'requires_attunement', 'tick_attunement', 'tracking_enabled',
]
