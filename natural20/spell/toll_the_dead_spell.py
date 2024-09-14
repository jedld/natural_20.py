from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.weapons import damage_modifier, target_advantage_condition
from natural20.utils.ac_utils import effective_ac
from natural20.spell.extensions.hit_computations import AttackSpell

class TollTheDeadSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.range = 60
        self.damage_type = "necrotic"

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }

    def _damage(self, battle, opts=None):
        entity = self.source
        level = 1
        if entity.level() >= 5:
            level += 1
        if entity.level() >= 11:
            level += 1
        if entity.level() >= 17:
            level += 1
        target = self.action.target
        if target.hp() < target.max_hp():
            return DieRoll.roll(f"{level}d12", battle=battle, entity=entity, description=self.t('dice_roll.spells.generic_damage', spell=self.t('spell.toll_the_dead')))

        return DieRoll.roll(f"{level}d8", battle=battle, entity=entity, description=self.t('dice_roll.spells.generic_damage', spell=self.t('spell.firebolt')))

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts).expected()


    def compute_hit_probability(self, battle, opts=None):
        """
        Compute the hit probability for the spell
        """
        target = self.action.target
        entity = self.source
        result = target.save_throw('wisdom', battle)

        return 1.0 - result.prob(entity.spell_save_dc("wisdom"))

    def resolve(self, entity, battle, spell_action):
            target = spell_action.target

            result = target.save_throw('wisdom', battle)
            spell_dc = entity.spell_save_dc("wisdom")
            if result < spell_dc:
                save_failed = True
            else:
                save_failed = False

            if save_failed:
                damage_roll = self._damage(battle)
                return [
                    {
                        'source': entity,
                        'target': target,
                        'attack_name': 'toll_the_dead',
                        'damage_type': self.properties['damage_type'],
                        'attack_roll': None,
                        'damage_roll': damage_roll,
                        'advantage_mod': None,
                        'adv_info': None,
                        'damage': damage_roll,
                        'spell_save': result,
                        'dc': spell_dc,
                        'cover_ac': None,
                        'type': 'spell_damage',
                        'spell': self.properties
                    }
                ]
            else:
                return [
                    {
                        'type': 'spell_miss',
                        'source': entity,
                        'target': target,
                        'attack_name': 'toll_the_dead',
                        'attack_roll': None,
                        'advantage_mod': None,
                        'adv_info': None,
                        'spell_save': result,
                        'dc': spell_dc,
                        'cover_ac': None
                    }
                ]
