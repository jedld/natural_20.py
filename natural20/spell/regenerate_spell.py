"""Regenerate (SRD) — 7th-level transmutation.

The target regains 1d4 hit points at the start of each of its turns for the
duration (1 hour). Limb regrowth is cosmetic in the VTT. The spell's casting
time (1 minute) already blocks use during battle via ``SpellAction.can_cast``.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


class RegenerateEffect:

    def __init__(self, source, target, spell_properties=None):
        self.source = source
        self.target = target
        self.spell_properties = dict(spell_properties or {})

    @property
    def id(self):
        return 'regenerate'

    def __str__(self):
        return self.id

    def label(self):
        return 'Regenerate'

    @staticmethod
    def start_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None or entity is None or entity.dead():
            return None
        dice = str(effect.spell_properties.get('heal_dice') or '1d4')
        roll = DieRoll.roll(dice, description='dice_roll.spells.regenerate',
                            entity=effect.source)
        amount = roll.result()
        if amount > 0:
            entity.heal(amount)
        return amount

    def register_hooks(self, duration=None):
        if self.target is not None:
            self.target.register_event_hook('start_of_turn', RegenerateEffect,
                                            effect=self, duration=duration)

    def restore_hooks(self):
        self.register_hooks()

    def dismiss(self, entity, descriptor=None, opts=None):
        target = entity if entity is not None else self.target
        if target is not None:
            for key, hooks in list(getattr(target, 'entity_event_hooks', {})
                                   .items()):
                target.entity_event_hooks[key] = [h for h in hooks
                                                  if h.get('effect') is not self]


class RegenerateSpell(Spell):

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
                     'attack_name': 'Regenerate', 'message': 'no_target',
                     'spell': self.properties}]
        return [{
            'type': 'regenerate', 'source': entity, 'target': target,
            'effect': self, 'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'regenerate':
            return None
        target = item.get('target')
        source = item.get('source')
        if target is None:
            return None
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 3600))
        target.remove_effect('regenerate')
        effect = RegenerateEffect(source, target, spell)
        target.register_effect('regenerate', RegenerateEffect, effect=effect,
                               source=source, duration=duration)
        target.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': (getattr(target, 'session', None).game_time
                                                 if getattr(target, 'session', None) else 0)
                                  + duration})
        effect.register_hooks(duration)
        session_evt = getattr(target, 'session', None)
        if session_evt is not None:
            session_evt.event_manager.received_event({
                'event': 'spell_buf', 'source': source, 'target': target,
                'spell': spell, 'effect_name': 'regenerate',
            })
        return effect
