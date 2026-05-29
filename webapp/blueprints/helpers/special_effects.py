"""Special-effect payload filtering helpers extracted from app.py."""

from .runtime_state import get_app

HEAVY_SPECIAL_EFFECTS = frozenset({'fog', 'rain', 'snow', 'water', 'point_fire'})


def special_effects_enabled():
    return bool(get_app().config.get('SPECIAL_EFFECTS_ENABLED', False))


def is_heavy_special_effect(effect_name):
    return effect_name in HEAVY_SPECIAL_EFFECTS


def filter_effect_payload(payload, stop_when_disabled=False):
    if not isinstance(payload, dict):
        return None

    effect_name = payload.get('effect')
    if special_effects_enabled() or not is_heavy_special_effect(effect_name):
        return dict(payload)

    if stop_when_disabled and effect_name:
        return {'effect': effect_name, 'action': 'stop'}

    return None


def filter_effect_payloads(payloads):
    filtered_payloads = []
    for payload in payloads or []:
        filtered = filter_effect_payload(payload)
        if filtered:
            filtered_payloads.append(filtered)
    return filtered_payloads


def has_enabled_effect_payloads(payloads):
    return bool(filter_effect_payloads(payloads))


def map_default_effect_payloads(battle_map):
    props = getattr(battle_map, 'properties', {}) or {}
    effect_defs = []
    payloads = []

    try:
        if isinstance(props.get('default_effects'), (list, tuple)):
            effect_defs.extend(props.get('default_effects') or [])
    except Exception:
        pass

    try:
        default_effect = props.get('default_effect')
        if default_effect:
            if isinstance(default_effect, (list, tuple)):
                effect_defs.extend(list(default_effect))
            else:
                effect_defs.append(default_effect)
    except Exception:
        pass

    for effect_def in effect_defs:
        try:
            payload = dict(effect_def)
        except Exception:
            continue
        payload['exclusive'] = False
        filtered = filter_effect_payload(payload)
        if filtered:
            payloads.append(filtered)

    return payloads


def point_fire_effect_payload(battle_map):
    props = getattr(battle_map, 'properties', {}) or {}
    point_fires = props.get('point_fires') or props.get('point_fire')

    if point_fires and isinstance(point_fires, (list, tuple)):
        return filter_effect_payload({
            'effect': 'point_fire',
            'action': 'start',
            'config': {'points': point_fires},
            'exclusive': False,
        }, stop_when_disabled=True)

    return {'effect': 'point_fire', 'action': 'stop'}
