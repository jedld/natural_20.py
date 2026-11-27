"""Frostbite (Xanathar's Guide) — cold cantrip, Constitution save.

A creature within 60 feet makes a Constitution saving throw. On a failure it
takes 1d8 cold damage (scaling to 4d8 at higher levels) and can't use
reactions until the start of your next turn. The reaction block is recorded
as the ``frostbitten`` status (visual/DM-facing in the VTT).
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell


class FrostbiteSpell(Spell):

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{'type': 'select_target', 'num': 1,
                       'range': self.properties.get('range', 60),
                       'target_types': ['enemies']}],
            'next': set_target,
        }

    def _damage(self, battle, entity, crit=False, estimated=False):
        level = 1
        cantrip_level = entity.cantrip_level() if hasattr(entity, 'cantrip_level') else 1
        for step in (5, 11, 17):
            if cantrip_level >= step:
                level += 1
        return DieRoll.roll(f'{level}d8', crit=crit, battle=battle, entity=entity,
                            description='dice_roll.spells.frostbite', estimated=estimated)

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, self.source, estimated=True).expected()

    def compute_hit_probability(self, battle, opts=None):
        target = self.action.target
        entity = self.source
        ability = HoldPersonSpell._caster_spell_ability(entity, self.action)
        result = target.save_throw('constitution', battle,
                                   {"is_magical": True, "estimated": True})
        return 1.0 - result.prob(entity.spell_save_dc(ability))

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        ability = HoldPersonSpell._caster_spell_ability(entity, spell_action)
        spell_dc = entity.spell_save_dc(ability)
        result = target.save_throw('constitution', battle,
                                   {"is_magical": True, "dc": spell_dc})
        save_failed = result < spell_dc
        if save_failed:
            from natural20.effects.timed_condition_effect import TimedConditionEffect
            TimedConditionEffect.apply_to(target, 'frostbitten',
                                          source=entity, battle=battle)
            damage_roll = self._damage(battle, entity)
            return [{
                'source': entity,
                'target': target,
                'attack_name': 'frostbite',
                'damage_type': self.properties.get('damage_type', 'cold'),
                'attack_roll': None,
                'damage_roll': damage_roll,
                'advantage_mod': None,
                'adv_info': None,
                'damage': damage_roll,
                'spell_save': result,
                'dc': spell_dc,
                'cover_ac': None,
                'type': 'spell_damage',
                'spell': self.properties,
            }]
        return [{
            'type': 'spell_miss',
            'source': entity,
            'target': target,
            'attack_name': 'frostbite',
            'damage_type': self.properties.get('damage_type', 'cold'),
            'attack_roll': None,
            'damage_roll': None,
            'advantage_mod': None,
            'adv_info': None,
            'spell_save': result,
            'dc': spell_dc,
            'spell': self.properties,
        }]
