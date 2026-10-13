"""Mass Healing Word — up to six creatures within 60 ft regain 1d4 + modifier HP.

Healing increases by 1d4 per slot level above 3rd. Each target gets its own
``spell_heal`` item (applied by ``CureWoundsSpell.apply``, so Disciple of
Life and the heal log work as for single-target healing). No effect on
undead or constructs.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


def _unhealable(target):
    races = [str(r).lower() for r in ((getattr(target, 'properties', None) or {}).get('race') or [])]
    return 'undead' in races or 'construct' in races


class MassHealingWordSpell(Spell):
    BASE_LEVEL = 3

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': int(self.properties.get('max_targets', 6)),
                'min': 1,
                'range': self.properties.get('range', 60),
                'unique_targets': True,
                'auto_pick': 'most_wounded',
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }

    def _dice(self):
        at_level = getattr(self.action, 'at_level', None) or self.properties.get('level', self.BASE_LEVEL)
        return 1 + max(0, int(at_level) - self.BASE_LEVEL)

    def _heal(self, battle):
        entity = self.source
        return DieRoll.roll(f"{self._dice()}d4+{entity.cleric_spell_casting_modifier()}",
                            battle=battle, entity=entity,
                            description='dice_roll.spells.mass_healing_word')

    @staticmethod
    def _targets(target):
        if target is None:
            return []
        if isinstance(target, (list, tuple)):
            out = []
            for t in target:
                if hasattr(t, 'heal') and t not in out:
                    out.append(t)
            return out
        return [target]

    def compute_hit_probability(self, battle, opts=None):
        return 1.0

    def avg_damage(self, battle, opts=None):
        targets = self._targets(getattr(self.action, 'target', None)) or [None]
        return -self._heal(None).expected() * len(targets)

    def resolve(self, entity, battle, spell_action, _battle_map):
        results = []
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', self.BASE_LEVEL)
        for target in self._targets(spell_action.target):
            if _unhealable(target):
                continue
            results.append({
                'source': entity,
                'target': target,
                'type': 'spell_heal',
                'heal_roll': self._heal(battle),
                'at_level': at_level,
                'spell': self.properties,
            })
        return results
