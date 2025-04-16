from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import after_attack_roll_hook
import pdb
class MagicMissileSpell(Spell):
    def build_map(self, orig_action):
        action = orig_action.clone()
        cast_level = action.at_level or 1
        darts = 3 + (cast_level - 1)

        def next_func(target):
            action.target = target
            return action

        return { 'param': [
            {'type': 'select_target',
             'num': darts,
             'range': self.properties['range'],
             'allow_retarget': True,
             'target_types': ['enemies']}
        ], 'next': next_func }

    def compute_hit_probability(self, battle, opts = None):
        return 1.0

    def resolve(self, entity, battle, spell_action, _battle_map):
        targets = spell_action.target

        result = []
        if not isinstance(targets, list) and not isinstance(targets, tuple):
            cast_level = self.action.at_level or 1
            recast_list = []
            for _ in range(3 + (cast_level - 1)):
                recast_list.append(targets)
            targets = recast_list
        # if there are tuples in targets, flatten them

        for target in targets:
            _, events = after_attack_roll_hook(battle, target, entity, None, None, opts={'magic_missile': True})
            for event in events:
                result.append(event)

            if target.has_spell_effect('shield'):
                result.append({
                    'source': entity,
                    'target': target,
                    'attack_name': self.t('spell.magic_missile'),
                    'damage_type': self.properties['damage_type'],
                    'type': 'spell_miss',
                    'spell': self.properties
                })
            else:
                damage_roll = DieRoll.roll('1d4+1', battle=battle, entity=entity,
                                           description=self.t('dice_roll.spells.magic_missile'))

                result.append({
                    'source': entity,
                    'target': target,
                    'attack_name': self.t('spell.magic_missile'),
                    'damage_type': self.properties['damage_type'],
                    'damage_roll': damage_roll,
                    'damage': damage_roll,
                    'type': 'spell_damage',
                    'spell': self.properties
                })

        return result
