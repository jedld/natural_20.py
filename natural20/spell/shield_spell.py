from natural20.spell.spell import Spell, consume_resource
from natural20.action import Action, AsyncReactionHandler
from natural20.actions.spell_action import SpellAction
import pdb
class ShieldSpell(Spell):
    ends_at_start_of_turn = True

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
    def is_active_on(entity):
        game_time = entity.session.game_time
        return any(
            e.get('handler') is ShieldSpell
            and (not e.get('expiration') or e['expiration'] > game_time)
            for e in entity.effects.get('ac_bonus', [])
        )

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

        if not battle:
            return [[], False]

        spell = battle.session.load_spell('shield')
        original_action = opts.get('original_action', None)

        if attack_roll is None or attack_roll.result() in range(effective_ac, effective_ac + 5):
            entity_controller = battle.controller_for(entity)
            if entity_controller is None:
                return [[], False]

            if ShieldSpell.is_active_on(entity):
                return [[], False]

            if not entity.conscious() or not entity.has_reaction(battle):
                return [[], False]

            if not SpellAction.can_cast(entity, battle, 'shield'):
                return [[], False]

            shield_spell = ShieldSpell(battle.session, entity, 'ShieldSpell', spell)
            action = SpellAction(battle.session, entity, 'spell')
            action.target = entity
            action.spell = spell
            action.at_level = spell.get('level', 1)
            slot_owner = entity.owner if entity.familiar() else entity
            if hasattr(slot_owner, 'next_spell_slot_level'):
                for klass in slot_owner.spell_list_classes_for(spell):
                    slot_level = slot_owner.next_spell_slot_level(klass.lower(), action.at_level)
                    if slot_level is not None:
                        action.at_level = slot_level
                        action.spellcasting_class = klass.lower()
                        break
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
                shield_spell.consume(battle)
                # The +5 AC already counts against the triggering attack.
                blocks_attack = (
                    attack_roll is not None
                    and effective_ac is not None
                    and not attack_roll.nat_20()
                    and attack_roll.result() < effective_ac + 5
                )
                return [[event], 'force_miss' if blocks_attack else False]
            else:
                return [[], False]
        else:
           return [[], False]

    def resolve(self, entity, battle, spell_action, _battle_map):
        return [{
            'type': 'shield',
            'target': spell_action.source,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties
        }]
