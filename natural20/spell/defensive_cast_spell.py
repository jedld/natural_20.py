"""Defensive Cast (PHB 2024): the reaction a caster takes when an attack hits.

One prepared spell, two options, offered when an attack roll would hit you:

* **Bolster** - temporary hit points (YAML ``temp_hp_base`` plus an optional
  ``temp_hp_ability`` modifier).
* **Defensive Dueling** - ``ac_bonus`` to AC (and optional ``speed_bonus``)
  until the start of your next turn; when the bonus turns the triggering
  attack into a miss the attack is forced to miss, like Shield.

The spell is YAML-driven (``defensive_cast_options`` list) so any similar
2024-style defensive reactions reuse this class. Like every reaction spell
it shares the engine's one-reaction-spell-per-turn budget
(``Battle.can_cast_reaction_spell``).
"""

from natural20.action import AsyncReactionHandler
from natural20.actions.spell_action import SpellAction
from natural20.spell.spell import Spell

REACTION_TYPE = 'defensive_cast'

DEFAULT_OPTIONS = [
    {'id': 'bolster', 'label': 'Bolster', 'temp_hp_base': 2},
    {'id': 'dueling', 'label': 'Defensive Dueling', 'ac_bonus': 2},
]


class DefensiveCastSpell(Spell):
    ends_at_start_of_turn = True

    def build_map(self, action):
        return action

    # -- option lookup ------------------------------------------------------

    @staticmethod
    def cast_option(spell_details, action=None):
        """The option this cast uses: explicit opt first, then the spell YAML
        or action props, then engine defaults (SRD-style)."""
        chosen = None
        if action is not None:
            chosen = (getattr(action, 'opts', None) or {}).get('cast_option')
        if isinstance(chosen, str):
            chosen = next((o for o in DefensiveCastSpell.options(spell_details)
                           if o.get('id') == chosen), None)
        if chosen:
            return dict(chosen)
        props = spell_details if isinstance(spell_details, dict) else {}
        for source in (props.get('spell_details'), props):
            if isinstance(source, dict):
                options = source.get('defensive_cast_options')
                if options:
                    return dict(options[0])
        return dict(DEFAULT_OPTIONS[0])

    @staticmethod
    def options(spell_details):
        options = (spell_details or {}).get('defensive_cast_options')
        return options or DEFAULT_OPTIONS

    @staticmethod
    def temp_hp_for(entity, option):
        base = int(option.get('temp_hp_base', 2) or 0)
        ability = option.get('temp_hp_ability')
        if ability:
            try:
                score = int((entity.ability_scores or {}).get(ability, 10))
                base += (score - 10) // 2
            except Exception:
                pass
        return max(base, 0)

    # -- effect handlers ------------------------------------------------------

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'defensive_cast':
            return
        effect = item['effect']
        option = getattr(effect, 'cast_option', None) or {}
        target = item['target']

        if option.get('temp_hp_base') is not None:
            amount = DefensiveCastSpell.temp_hp_for(target, option)
            if battle is not None and amount > 0:
                state = battle.entity_state_for(target)
                if state is not None:
                    state['temp_hp'] = int(state.get('temp_hp') or 0) + amount
                    item.setdefault('temp_hp', amount)
                    battle.session.event_manager.received_event({
                        "event": 'temp_hp',
                        "source": item['source'],
                        "target": target,
                        "amount": amount})
            return

        target.register_effect('ac_bonus', DefensiveCastSpell,
                               effect=item['effect'], duration=60)
        if option.get('speed_bonus'):
            target.register_effect('speed_override', DefensiveCastSpell,
                                   effect=item['effect'], duration=60)
        target.register_event_hook('start_of_turn', DefensiveCastSpell,
                                   effect=item['effect'], source=item['source'])
        battle.session.event_manager.received_event({
            "event": 'spell_buf', "spell": item['effect'],
            "source": item['source'],
            "target": target})

    @staticmethod
    def ac_bonus(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        option = getattr(effect, 'cast_option', None) or {}
        return int(opt.get('value') or 0) + int(option.get('ac_bonus') or 0)

    @staticmethod
    def speed_override(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        option = getattr(effect, 'cast_option', None) or {}
        return int(opt.get('value') or 0) + int(option.get('speed_bonus') or 0)

    @staticmethod
    def start_of_turn(entity, opts=None):
        if opts is None:
            opts = {}
        entity.dismiss_effect(opts['effect'])

    # -- reaction window ------------------------------------------------------

    @staticmethod
    def after_attack_roll(battle, entity, attacker, attack_roll, effective_ac, opts=None):
        """Offer Bolster / Defensive Dueling when an attack roll would hit."""
        if opts is None:
            opts = {}
        if not battle or attack_roll is None:
            return [[], False]

        # Defensive Cast triggers on a successful hit (2024), not a near miss.
        if not attack_roll.nat_20() and attack_roll.result() < effective_ac:
            return [[], False]

        entity_controller = battle.controller_for(entity)
        if entity_controller is None:
            return [[], False]
        if not entity.conscious() or not entity.has_reaction(battle):
            return [[], False]
        if not battle.can_cast_reaction_spell(entity):
            return [[], False]

        spell = battle.session.load_spell('defensive_cast')
        if not spell:
            return [[], False]
        if not SpellAction.can_cast(entity, battle, 'defensive_cast'):
            return [[], False]

        # Dueling only helps when its AC bonus saves the attack; Bolster is
        # always worth offering against a hit.
        applicable = []
        for option in DefensiveCastSpell.options(spell):
            if option.get('ac_bonus'):
                if not attack_roll.nat_20() and \
                        attack_roll.result() < effective_ac + int(option['ac_bonus']):
                    applicable.append(option)
            elif option.get('temp_hp_base') is not None:
                applicable.append(option)
        if not applicable:
            return [[], False]

        spell_actions = []
        for option in applicable:
            action = SpellAction(battle.session, entity, 'spell')
            action.target = entity
            action.spell = spell
            action.at_level = spell.get('level', 1)
            action.as_reaction = True
            action.opts = {'cast_option': option}
            slot_owner = entity.owner if entity.familiar() else entity
            if hasattr(slot_owner, 'next_spell_slot_level'):
                for klass in slot_owner.spell_list_classes_for(spell):
                    slot_level = slot_owner.next_spell_slot_level(klass.lower(), action.at_level)
                    if slot_level is not None:
                        action.at_level = slot_level
                        action.spellcasting_class = klass.lower()
                        break
            instance = DefensiveCastSpell(battle.session, entity, 'DefensiveCastSpell', spell)
            instance.cast_option = option
            instance.action = action
            action.spell_action = instance
            spell_actions.append(action)

        event = {
            'type': REACTION_TYPE,
            'target': entity,
            'source': entity,
            'trigger': REACTION_TYPE,
            'attacker': attacker,
            'spell': spell,
        }
        original_action = opts.get('original_action', None)
        if original_action:
            stored_reaction = original_action.has_async_reaction_for_source(entity, REACTION_TYPE)
            result = stored_reaction if stored_reaction is not False else entity_controller.select_reaction(
                entity, battle, battle.map_for(entity), spell_actions, event
            )
        elif hasattr(entity_controller, 'select_reaction'):
            result = entity_controller.select_reaction(
                entity, battle, battle.map_for(entity), spell_actions, event
            )
        else:
            result = entity_controller.select_action(battle, entity, spell_actions)

        if hasattr(result, 'send'):
            raise AsyncReactionHandler(entity, result, original_action, REACTION_TYPE)
        if not result:
            return [[], False]

        instance = result.spell_action
        option = instance.cast_option
        instance.consume(battle)

        event['cast_option'] = option
        event['effect'] = instance
        events = [event]

        blocks_attack = False
        if option.get('ac_bonus'):
            blocks_attack = (
                not attack_roll.nat_20()
                and attack_roll.result() < effective_ac + int(option['ac_bonus'])
            )
        return events, ('force_miss' if blocks_attack else False)

    # -- normal resolution (commit applies the option) --------------------------

    def resolve(self, entity, battle, spell_action, _battle_map):
        self.cast_option = DefensiveCastSpell.cast_option(
            self.properties, spell_action)
        return [{
            'type': 'defensive_cast',
            'target': spell_action.source,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties,
        }]


def choose_defensive_cast_option(entity, battle, valid_actions, event=None):
    """Heuristic pick for AI controllers.

    The engine only offers the AC option when it turns the triggering attack
    into a miss, so negating the attack outright beats soaking the damage.
    """
    if not valid_actions:
        return None
    for action in valid_actions:
        option = (getattr(action, 'opts', None) or {}).get('cast_option') or {}
        if option.get('ac_bonus'):
            return action
    return valid_actions[0]
