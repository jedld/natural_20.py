"""Effect-driven action restrictions.

An effect can forbid whole categories of actions by registering an
``action_restriction`` effect whose handler returns the restricted kinds
(it receives ``opts['value']`` — the kinds collected so far — and should
return that list extended with its own)::

    target.register_effect('action_restriction', GaseousFormSpell, effect=effect, ...)

    @staticmethod
    def action_restriction(entity, opt=None):
        return list((opt or {}).get('value') or []) + ['attack', 'spell', 'speak', 'interact']

Kinds checked by the engine:

* ``attack`` — ``AttackAction.can`` (weapon and natural attacks)
* ``spell`` — ``SpellAction.can_cast``
* ``speak`` — ``SpeakAction.can``
* ``interact`` — ``InteractAction.can`` (manipulating objects)
"""
from __future__ import annotations

RESTRICTION_EFFECT = 'action_restriction'


def restricted_kinds(entity) -> list:
    if entity is None or not hasattr(entity, 'has_effect'):
        return []
    try:
        if not entity.has_effect(RESTRICTION_EFFECT):
            return []
        kinds = entity.eval_effect(RESTRICTION_EFFECT, {'stacked': True, 'value': []})
    except Exception:
        return []
    return list(kinds or [])


def is_restricted(entity, kind) -> bool:
    return kind in restricted_kinds(entity)
