from natural20.spell.spell import Spell, consume_resource
from natural20.action import Action, AsyncReactionHandler
from natural20.actions.spell_action import SpellAction
import pdb
class ShieldSpell(Spell):
    def build_map(self, action):
        return action

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'shield':
            item['source'].add_casted_effect({ "target" : item['source'], "effect" : item['effect']})
            item['target'].register_effect('ac_bonus', ShieldSpell, effect=item['effect'], source=item['source'], duration=8 * 60 * 60)

            item['target'].register_event_hook('start_of_turn', ShieldSpell, effect=item['effect'], source=item['source'])
            battle.session.event_manager.received_event({
                "event": 'spell_buf', "spell": item['effect'],
                "source": item['source'],
                "target": item['source']})

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
        original_action = opts.get('original_action', None)
        if attack_roll is None or attack_roll.result() in range(effective_ac, effective_ac + 5):
            entity_controller = battle.controller_for(entity)
            if entity_controller is None:
                return [[], False]

            if entity.has_effect(ShieldSpell):
                return [[], False]

            shield_spell = ShieldSpell(battle.session, entity, 'ShieldSpell', spell)
            action = SpellAction(battle.session, entity, 'spell')
            action.target = entity
            shield_spell.action = action
            action.spell_action = shield_spell
            valid_actions = [action]
            event = {
                'type': 'shield',
                'target': entity,
                'source': entity,
                'effect': shield_spell,
                'spell': spell,
                'trigger': 'shield'
            }
            if original_action:
                stored_reaction = original_action.has_async_reaction_for_source(entity, 'shield')
                result = stored_reaction if stored_reaction is not False else entity_controller.select_reaction(
                    entity, battle, battle.map_for(entity), valid_actions, event
                )
            else:
                result = entity_controller.select_action(battle, entity, valid_actions)

            if hasattr(result, 'send'):
                raise AsyncReactionHandler(entity, result, original_action, 'shield')
            if result:
                return [[event], False]
            else:
                return [[], False]
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
