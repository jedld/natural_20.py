"""Rune Strike (Dragonlance: Shadow of the Dragon Queen) — 1st-level evocation.

Make a melee spell attack against a creature you can reach. On a hit the
target takes 2d8 necrotic damage; the damage rises to 3d8 against a
celestial, and by 1d8 per slot level above 1st.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.spell.spell import Spell  # re-export friendly
from natural20.utils.spell_attack_util import evaluate_spell_attack, spell_attack_is_critical


class RuneStrikeSpell(AttackSpell):

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{'type': 'select_target', 'num': 1, 'range': 5,
                       'target_types': ['enemies']}],
            'next': set_target,
        }

    def _is_celestial(self, target):
        types = set()
        try:
            from natural20.spell.condition_spells import _creature_types
            types = {str(t).lower() for t in (_creature_types(target) or [])}
        except Exception:
            pass
        race = getattr(target, 'race', None)
        if callable(race):
            try:
                race = race()
            except Exception:
                race = None
        if isinstance(race, (list, tuple, set)):
            types |= {str(r).lower() for r in race}
        return 'celestial' in types

    def _dice(self, at_level, celestial):
        n = 2 + max(0, int(at_level or 1) - 1)
        if celestial:
            n += 1
        return f'{n}d8'

    def _damage(self, battle, target, crit=False, opts=None, estimated=False):
        opts = opts or {}
        at_level = opts.get('at_level', 1)
        return DieRoll.roll(self._dice(at_level, self._is_celestial(target)),
                            crit=crit, battle=battle, entity=self.source,
                            description='dice_roll.spells.rune_strike',
                            estimated=estimated)

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, self.action.target, opts=opts,
                            estimated=True).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        result = []
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = \
            evaluate_spell_attack(self.session, entity, target, self.properties,
                                  battle=battle, opts={"action": spell_action})
        for event in events:
            result.append(event)

        if hit:
            damage_roll = self._damage(
                battle, target,
                crit=spell_attack_is_critical(attack_roll, entity, target, battle),
                opts={'at_level': getattr(spell_action, 'at_level', 1)})
            result.append({
                'source': entity,
                'target': target,
                'attack_name': 'Rune Strike',
                'damage_type': self.properties.get('damage_type', 'necrotic'),
                'attack_roll': attack_roll,
                'damage_roll': damage_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'damage': damage_roll,
                'cover_ac': cover_ac_adjustments,
                'type': 'spell_damage',
                'spell': self.properties,
            })
        else:
            result.append({
                'type': 'spell_miss',
                'source': entity,
                'target': target,
                'attack_name': 'Rune Strike',
                'damage_type': self.properties.get('damage_type', 'necrotic'),
                'attack_roll': attack_roll,
                'damage_roll': None,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'cover_ac': cover_ac_adjustments,
                'spell': self.properties,
            })
        return result
