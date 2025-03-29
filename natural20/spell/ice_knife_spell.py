from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.spell.extensions.hit_computations import AttackSpell
import pdb

class IceKnifeSpell(AttackSpell):
    def build_map(self, orig_action):
        def set_target(target):
            if not target:
                raise ValueError("Invalid target")

            action = orig_action.clone()
            action.target = target
            return action
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies'],
                },
            ],
            'next': set_target,
        }

    def _damage(self, battle, opts=None):
        entity = self.source
        return DieRoll.roll("1d10", battle=battle, entity=entity, description="dice_roll.spells.ice_knife")

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info = evaluate_spell_attack(battle, entity, target, self.properties, opts={"action": spell_action})

        if hit:
            damage_roll = self._damage(battle)
            return [{
                'source': entity,
                'target': target,
                'attack_name': "spell.ice_knife",
                'damage_type': self.properties['damage_type'],
                'attack_roll': attack_roll,
                'damage_roll': damage_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'damage': damage_roll,
                'cover_ac': cover_ac_adjustments,
                'type': 'spell_damage',
                'spell': self.properties,
            },
            {
                'source': entity,
                'target': target,
                'type': 'ice_knife',
                'at_level': self.action.at_level,
                'effect': self,
                'attack_roll': attack_roll,
            }]
        else:
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': target,
                'attack_name': "spell.ice_knife",
                'damage_type': self.properties['damage_type'],
                'attack_roll': attack_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'cover_ac': cover_ac_adjustments,
                'spell': self.properties,
            },{
                'source': entity,
                'target': target,
                'type': 'ice_knife',
                'at_level': self.action.at_level,
                'effect': self,
                'attack_roll': attack_roll,
            }]

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'ice_knife':
            map = battle.map_for(item['source'])

            # On hit, the target and all creatures within 5 feet of the target must make a Dexterity saving throw.
            affected_entities = [item['target']] + map.entities_in_range(item['target'], 5)
            attack_roll = item['attack_roll']
            for entity in affected_entities:
                saving_throw = entity.saving_throw('dexterity', battle)
                level = item['at_level'] + 1
                if saving_throw.result() < item['source'].spell_save_dc():
                    session.event_manager.received_event({
                        'event': 'ice_knife',
                        'source': item['source'],
                        'target': entity,
                        'roll': saving_throw,
                        'save_type': 'dexterity',
                        'success': False,
                    })

                    damage_roll = DieRoll.roll(f"{level}d6", description='dice_roll.spells.ice_knife', entity=item['source'], battle=battle)
                    entity.take_damage(damage_roll.result(),
                                               damage_type='cold',
                                               critical=attack_roll.nat_20(),
                                               roll_info=damage_roll,
                                               session=session,
                                               battle=battle)
                else:
                    session.event_manager.received_event({
                        'event': 'ice_knife',
                        'source': item['source'],
                        'target': entity,
                        'roll': saving_throw,
                        'save_type': 'dexterity',
                        'success': True,
                    })