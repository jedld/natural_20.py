from natural20.spell.spell import Spell, consume_resource
from natural20.action import Action
import pdb
class ShieldSpell(Spell):
    def build_map(self, action):
        return action

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'shield':
            item['source'].add_casted_effect(effect=item['effect'])
            item['target'].register_effect('ac_bonus', ShieldSpell, effect=item['effect'], source=item['source'], duration=8 * 60 * 60)

            item['target'].register_event_hook('start_of_turn', ShieldSpell, effect=item['effect'], source=item['source'])
            battle.session.event_manager.received_event({
                "event": 'spell_buf', "spell": item['effect'],
                "source": item['source'],
                "target": item['source']})
            consume_resource(battle, item)

    @staticmethod
    def ac_bonus(entity, effect):
        return 5

    @staticmethod
    def start_of_turn(entity, opts=None):
        if opts is None:
            opts = {}
        entity.dismiss_effect(opts['effect'])

    @staticmethod
    def after_attack_roll(battle, entity, attacker, attack_roll, effective_ac, opts=None):
        if opts is None:
            opts = {}

        spell = battle.session.load_spell('shield')
        if attack_roll is None or attack_roll.result in range(effective_ac, effective_ac + 5):
            print("Shield spell avaialble as a reaction")
            pdb.set_trace()
            #TODO: Add prompt to use shield spell
            shield_spell = ShieldSpell(battle.session, entity, 'shield', spell)
            action = Action(battle.session, entity, 'spell')
            action.target = entity
            shield_spell.action = action
            return [[{
                'type': 'shield',
                'target': entity,
                'source': entity,
                'effect': shield_spell,
                'spell': spell
            }], False]
        else:
            return [[], False]

    def resolve(self, entity, battle, spell_action):
        return [{
            'type': 'shield',
            'target': spell_action.source,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties
        }]
