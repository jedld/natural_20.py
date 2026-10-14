"""Limited "fail a save, choose to succeed instead" traits (race / creature YAML).

    save_auto_success:
      - feature: fearless          # race feature the creature must have
        condition: frightened      # only saves against this condition
        pool: fearless             # resource pool spent per use
      - feature: some_trait
        abilities: [wisdom]        # or restrict by save ability

The pool is registered from the race ``resource_pools`` block
(``natural20/utils/giant_ancestry.py``).
"""

from __future__ import annotations


def _specs(entity):
    out = []
    race_props = getattr(entity, 'race_properties', None) or {}
    out.extend(race_props.get('save_auto_success') or [])
    subrace = entity.subrace() if callable(getattr(entity, 'subrace', None)) else None
    if subrace:
        out.extend(((race_props.get('subrace') or {}).get(subrace) or {}).get('save_auto_success') or [])
    if not race_props:
        out.extend((getattr(entity, 'properties', None) or {}).get('save_auto_success') or [])
    return [s for s in out if isinstance(s, dict)]


def _save_conditions(opts):
    conditions = set()
    for key in ('condition', 'saving_throw_type'):
        if opts.get(key):
            conditions.add(str(opts[key]))
    extra = opts.get('conditions')
    if isinstance(extra, (list, tuple)):
        conditions.update(str(c) for c in extra)
    return conditions


def _matches(entity, spec, save_type, opts):
    feature = spec.get('feature')
    if feature:
        try:
            if not entity.class_feature(feature):
                return False
        except Exception:
            return False
    condition = spec.get('condition')
    if condition and condition not in _save_conditions(opts):
        return False
    abilities = spec.get('abilities')
    if abilities and save_type not in abilities:
        return False
    pool = spec.get('pool')
    if pool:
        res = entity.get_resource(pool) if hasattr(entity, 'get_resource') else None
        if res is None or res.current <= 0:
            return False
    return True


def try_save_auto_success(entity, save_roll, dc, save_type, opts, battle=None):
    """Turn a failed save into a success via a matching ``save_auto_success`` entry."""
    try:
        total = save_roll.result()
        dc = int(dc)
    except Exception:
        return save_roll
    if total >= dc:
        return save_roll
    for spec in _specs(entity):
        if not _matches(entity, spec, save_type, opts or {}):
            continue
        if spec.get('pool'):
            entity.consume_resource(spec['pool'])
        from natural20.die_roll import DieRoll
        label = spec.get('feature') or 'auto_success'
        adjusted = save_roll + DieRoll.roll(f"+{dc - total}", description=label,
                                            entity=entity, battle=battle)
        if getattr(adjusted, 'metadata', None) is None:
            adjusted.metadata = {}
        adjusted.metadata.update(getattr(save_roll, 'metadata', None) or {})
        adjusted.metadata['auto_success'] = label
        session = getattr(entity, 'session', None)
        if session is not None:
            session.event_manager.received_event({
                'source': entity, 'event': 'save_auto_success',
                'feature': label, 'save_type': save_type, 'roll': save_roll, 'dc': dc,
            })
        return adjusted
    return save_roll
