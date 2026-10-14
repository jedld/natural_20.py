"""Blade Ward — abjuration cantrip, two editions picked by YAML ``blade_ward.mode``.

* ``resistance`` (2014 SRD): resistance to bludgeoning, piercing and slashing
  damage until the end of the caster's next turn (``duration_seconds: 6``).
  Applied to all damage of those types, not only weapon attacks.
* ``attack_penalty`` (2024): concentration up to 1 minute; any creature
  attacking the caster subtracts ``dice`` (1d4) from the attack roll
  (``targeted_attack_penalty``, ``natural20/utils/attack_penalties.py``).
"""
from __future__ import annotations

from natural20.spell.spell import Spell

EFFECT_KEY = 'blade_ward'


class BladeWardEffect:
    def __init__(self, source, spell_properties):
        self.source = source
        self.spell_properties = dict(spell_properties or {})

    @property
    def id(self):
        return 'blade_ward'

    def __str__(self):
        return 'blade_ward'

    def _rule(self):
        return self.spell_properties.get('blade_ward') or {}

    @staticmethod
    def resistance_override(entity, opts=None):
        opts = opts or {}
        base = list(opts.get('value') or [])
        effect = opts.get('effect')
        types = (effect._rule().get('damage_types') if effect is not None else None) \
            or ['bludgeoning', 'piercing', 'slashing']
        for damage_type in types:
            if damage_type not in base:
                base.append(damage_type)
        return base

    @staticmethod
    def targeted_attack_penalty(entity, opts=None):
        effect = (opts or {}).get('effect')
        return (effect._rule().get('dice') if effect is not None else None) or '1d4'

    def dismiss(self, entity, _descriptor=None, opts=None):
        for key in ('resistance_override', 'targeted_attack_penalty', EFFECT_KEY):
            entity.effects[key] = [d for d in entity.effects.get(key, []) if d.get('effect') is not self]
        if EFFECT_KEY in entity.statuses:
            entity.statuses.remove(EFFECT_KEY)


class BladeWardSpell(Spell):
    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = self.source
        return action

    def resolve(self, entity, battle, spell_action, battle_map):
        return [{'type': 'blade_ward', 'source': entity, 'target': entity, 'spell': self.properties,
                 'effect': self}]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'blade_ward':
            return None
        source = item['source']
        session = session or (battle.session if battle is not None else source.session)
        spell = item.get('spell') or {}
        rule = spell.get('blade_ward') or {}
        mode = rule.get('mode', 'resistance')
        duration = int(spell.get('duration_seconds', 6 if mode == 'resistance' else 60))
        source.remove_effect(EFFECT_KEY)
        effect = BladeWardEffect(source, spell)
        handler_key = 'resistance_override' if mode == 'resistance' else 'targeted_attack_penalty'
        source.register_effect(handler_key, BladeWardEffect, effect=effect, source=source, duration=duration)
        source.register_effect(EFFECT_KEY, BladeWardEffect, effect=effect, source=source, duration=duration)
        if EFFECT_KEY not in source.statuses:
            source.statuses.append(EFFECT_KEY)
        source.add_casted_effect({'target': source, 'effect': effect,
                                  'expiration': session.game_time + duration})
        if spell.get('concentration'):
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)
        session.event_manager.received_event({'event': 'spell_buf', 'source': source, 'target': source,
                                              'spell': spell})
        return source
