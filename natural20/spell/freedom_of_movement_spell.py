"""Freedom of Movement (SRD) — 4th-level abjuration buff.

For the duration the target's movement is unaffected by difficult terrain and
magical speed reducers, spells cannot paralyze or restrain it, and being
underwater imposes no movement penalties. Engine wiring:

- ``Map.difficult_terrain`` skips terrain/object difficulty and zone speed
  halves for creatures carrying this effect (entity crowding still applies).
- ``Entity.immune_to_condition`` sees the effect's ``condition_immunity``
  handler for ``paralyzed`` / ``restrained`` / ``grappled`` (SRD grants the
  automatic 5-foot escape from nonmagical grapples, which we approximate by
  refusing the grapple outright).
"""
from __future__ import annotations

from natural20.spell.spell import Spell


class FreedomOfMovementEffect:

    def __init__(self, source, spell_properties=None):
        self.source = source
        self.spell_properties = dict(spell_properties or {})

    @property
    def id(self):
        return 'freedom_of_movement'

    def __str__(self):
        return self.id

    def label(self):
        return 'Freedom of Movement'

    @staticmethod
    def condition_immunity(entity, opt=None):
        opt = opt or {}
        return list(opt.get('value') or []) + ['paralyzed', 'restrained', 'grappled']

    @staticmethod
    def freedom_of_movement(entity, opt=None):
        return True

    def dismiss(self, entity, descriptor=None, opts=None):
        statuses = getattr(entity, 'statuses', None)
        if isinstance(statuses, list) and 'freedom_of_movement' in statuses:
            statuses.remove('freedom_of_movement')


class FreedomOfMovementSpell(Spell):

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{'type': 'select_target', 'num': 1, 'range': 5,
                       'target_types': ['allies', 'self']}],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if target is None or isinstance(target, (list, tuple)):
            return [{'type': 'spell_miss', 'source': entity, 'target': entity,
                     'attack_name': 'Freedom of Movement', 'message': 'no_target',
                     'spell': self.properties}]
        return [{
            'type': 'freedom_of_movement', 'source': entity, 'target': target,
            'effect': self, 'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'freedom_of_movement':
            return None
        target = item.get('target')
        source = item.get('source')
        if target is None:
            return None
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 28800))
        target.remove_effect('freedom_of_movement')
        target.remove_effect('condition_immunity')
        effect = FreedomOfMovementEffect(source, spell)
        target.register_effect('freedom_of_movement', FreedomOfMovementEffect,
                               effect=effect, source=source, duration=duration)
        # Entity.immune_to_condition reads the stacked condition_immunity effect.
        target.register_effect('condition_immunity', FreedomOfMovementEffect,
                               effect=effect, source=source, duration=duration)
        target.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': (getattr(target, 'session', None).game_time
                                                 if getattr(target, 'session', None) else 0)
                                  + duration})
        session = getattr(target, 'session', None) or session
        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_buf', 'source': source, 'target': target,
                'spell': spell, 'effect_name': 'freedom_of_movement',
            })
        return effect
