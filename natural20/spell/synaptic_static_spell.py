"""Synaptic Static — psychic burst that leaves survivors' thoughts muddled.

20-ft-radius sphere, Intelligence save for half of 8d6 psychic. A creature
that fails is *muddled* for ``muddled.duration_seconds`` (1 minute): it
subtracts ``muddled.dice`` (1d6) from attack rolls (``attack_roll_penalty``)
and from Constitution saves to keep concentration
(``concentration_save_penalty``), and repeats the save at the end of each of
its turns. The ability-check penalty is not modelled.
"""
from __future__ import annotations

from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.wizard_spells import AreaSaveSpell, _spell_dc

EFFECT_KEY = 'muddled'


class MuddledEffect:
    def __init__(self, source, target, dc, dice='1d6', duration=60, save='intelligence'):
        self.source = source
        self.target = target
        self.dc = int(dc)
        self.dice = str(dice)
        self.duration = int(duration)
        self.save = save
        self.ended = False

    @property
    def id(self):
        return 'muddled'

    def __str__(self):
        return 'muddled'

    @staticmethod
    def attack_roll_penalty(entity, opts=None):
        effect = (opts or {}).get('effect')
        return effect.dice if effect is not None else '1d6'

    concentration_save_penalty = attack_roll_penalty

    def afflict(self):
        target = self.target
        for key in ('attack_roll_penalty', 'concentration_save_penalty', EFFECT_KEY):
            method = 'attack_roll_penalty' if key == EFFECT_KEY else key
            target.register_effect(key, MuddledEffect, method_name=method, effect=self,
                                   source=self.source, duration=self.duration)
        if EFFECT_KEY not in target.statuses:
            target.statuses.append(EFFECT_KEY)
        self.register_hooks()

    def register_hooks(self):
        self.target.register_event_hook('end_of_turn', self, method_name='on_end_of_turn',
                                        effect=self, source=self.source, duration=self.duration)

    def restore_hooks(self):
        if not self.ended and self.target is not None and hasattr(self.target, 'register_event_hook'):
            self.register_hooks()

    def on_end_of_turn(self, entity, opt=None):
        if self.ended:
            return
        save = SaveCheck.make(entity, self.save, self.dc, battle=(opt or {}).get('battle'),
                              opts={'is_magical': True})
        if save.passed:
            self.end(entity)

    def end(self, entity):
        self.ended = True
        for key in ('attack_roll_penalty', 'concentration_save_penalty', EFFECT_KEY):
            entity.effects[key] = [d for d in entity.effects.get(key, []) if d.get('effect') is not self]
        for key, hooks in list(entity.entity_event_hooks.items()):
            entity.entity_event_hooks[key] = [h for h in hooks if h.get('effect') is not self]
        if EFFECT_KEY in entity.statuses:
            entity.statuses.remove(EFFECT_KEY)
        entity.casted_effects = [f for f in entity.casted_effects if f.get('effect') is not self]
        entity.session.event_manager.received_event({
            'event': 'effect_ended', 'source': self.source, 'target': entity, 'effect_name': 'muddled',
        })

    def dismiss(self, entity, _descriptor=None, opts=None):
        if not self.ended:
            self.end(entity)


class SynapticStaticSpell(AreaSaveSpell):
    BASE_DAMAGE = '8d6'
    PER_SLOT_DAMAGE = '0d6'
    BASE_LEVEL = 5
    SHAPE = 'radius'
    SAVE = 'intelligence'
    DAMAGE_TYPE = 'psychic'

    def resolve(self, entity, battle, spell_action, battle_map):
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', self.BASE_LEVEL)
        targets = self._target_entities(entity, battle_map, spell_action.target)
        dc = _spell_dc(entity, spell_action)
        muddled = self.properties.get('muddled') or {}

        def on_failure(target, _damage):
            return [{'type': 'muddled', 'source': entity, 'target': target, 'dc': dc,
                     'dice': muddled.get('dice', '1d6'),
                     'duration': int(muddled.get('duration_seconds', 60)),
                     'spell': self.properties, 'effect': self}]

        return self.resolve_save_for_half(
            targets, ability=self.SAVE, dc=dc,
            damage_roll=lambda _t: self._damage(battle, opts={'at_level': at_level}),
            attack_name=self.properties.get('id', 'synaptic_static'),
            damage_type=self.DAMAGE_TYPE, battle=battle, on_failure=on_failure,
        )

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'muddled':
            return None
        target = item['target']
        if target.dead():
            return None
        session = session or (battle.session if battle is not None else target.session)
        for entry in list(target.effects.get(EFFECT_KEY, [])):
            old = entry.get('effect')
            if isinstance(old, MuddledEffect):
                old.end(target)
        effect = MuddledEffect(item['source'], target, item.get('dc', 10), item.get('dice', '1d6'),
                               item.get('duration', 60))
        effect.afflict()
        target.casted_effects.append({'target': target, 'effect': effect,
                                      'expiration': session.game_time + effect.duration})
        session.event_manager.received_event({'event': 'spell_debuff', 'spell': item.get('effect'),
                                              'source': item['source'], 'target': target})
        return effect
