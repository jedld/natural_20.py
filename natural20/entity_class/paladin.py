# pyright: reportAttributeAccessIssue=false

from collections import OrderedDict
from typing import TYPE_CHECKING

from natural20.action import AsyncReactionHandler
from natural20.actions.divine_smite_action import DivineSmiteAction
from natural20.actions.lay_on_hands_action import LayOnHandsAction

if TYPE_CHECKING:
    from natural20.player_character import PlayerCharacter

PALADIN_SPELL_SLOT_TABLE = [
        [0, 0],  # 1 - No spellcasting
        [0, 2],  # 2 - 2 slots at 1st level
        [0, 3],  # 3 - 3 slots at 1st level
        [0, 3],  # 4 - 3 slots at 1st level
        [0, 4, 2],  # 5 - 4 slots at 1st level, 2 at 2nd
        [0, 4, 2],  # 6 - 4 slots at 1st level, 2 at 2nd
        [0, 4, 3],  # 7 - 4 slots at 1st level, 3 at 2nd
        [0, 4, 3],  # 8 - 4 slots at 1st level, 3 at 2nd
        [0, 4, 3, 2],  # 9 - 4 slots at 1st level, 3 at 2nd, 2 at 3rd
        [0, 4, 3, 2],  # 10 - 4 slots at 1st level, 3 at 2nd, 2 at 3rd
        [0, 4, 3, 3],  # 11 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd
        [0, 4, 3, 3],  # 12 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd
        [0, 4, 3, 3, 1],  # 13 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 1 at 4th
        [0, 4, 3, 3, 1],  # 14 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 1 at 4th
        [0, 4, 3, 3, 2],  # 15 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 2 at 4th
        [0, 4, 3, 3, 2],  # 16 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 2 at 4th
        [0, 4, 3, 3, 3, 1],  # 17 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 3 at 4th, 1 at 5th
        [0, 4, 3, 3, 3, 1],  # 18 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 3 at 4th, 1 at 5th
        [0, 4, 3, 3, 3, 2],  # 19 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 3 at 4th, 2 at 5th
        [0, 4, 3, 3, 3, 2]  # 20 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 3 at 4th, 2 at 5th
    ]

class DivineSmiteEffect:
    def __init__(self, owner):
        self.owner = owner

    def on_attack_hit(self, entity, opts=None):
        if opts is None:
            opts = {}

        if entity != self.owner:
            return []

        hit_result = opts.get('result') or {}

        if not hit_result.get('hit?'):
            return []

        battle = hit_result.get('battle')
        if battle is None:
            return []

        target = hit_result.get('target')
        if target is None:
            return []

        if not self._is_valid_melee_hit(entity, hit_result):
            return []

        if entity.total_bonus_actions(battle) <= 0:
            return []

        available_slots = self._available_slot_levels(entity)
        if not available_slots:
            return []

        spell_details = entity.session.load_spell('divine_smite')
        valid_actions = [
            self._build_action(entity, target, slot_level, spell_details, hit_result)
            for slot_level in available_slots
        ]

        stored_reaction = opts.get('stored_reaction')
        attack_action = opts.get('action')
        controller = battle.controller_for(entity)

        if stored_reaction not in (None, False):
            selected_action = stored_reaction
        else:
            if controller is None:
                selected_action = valid_actions[0]
            else:
                event_payload = {
                    'type': 'divine_smite',
                    'trigger': 'on_attack_hit',
                    'source': entity,
                    'target': target,
                    'result': hit_result,
                    'spell': spell_details
                }
                selected_action = controller.select_reaction(
                    entity,
                    battle,
                    battle.map_for(entity),
                    valid_actions,
                    event_payload
                )

        if hasattr(selected_action, 'send'):
            raise AsyncReactionHandler(entity, selected_action, attack_action, 'on_attack_hit')

        if not selected_action:
            return []

        if isinstance(selected_action, list):
            return selected_action

        if isinstance(selected_action, int):
            if 0 <= selected_action < len(valid_actions):
                selected_action = valid_actions[selected_action]
            else:
                return []

        if not isinstance(selected_action, DivineSmiteAction):
            return []

        resolved_action = selected_action.resolve(entity.session, battle.map_for(entity), {'battle': battle})
        return resolved_action.result if resolved_action.result else []

    def _available_slot_levels(self, entity) -> list[int]:
        slot_owner = entity.owner if entity.familiar() else entity
        slots = getattr(slot_owner, 'spell_slots', {}).get('paladin', {})
        return [level for level, qty in sorted(slots.items()) if level > 0 and qty > 0]

    def _is_valid_melee_hit(self, entity, hit_result) -> bool:
        if hit_result.get('thrown'):
            return False

        weapon_meta = None
        if hit_result.get('npc_action'):
            weapon_meta = hit_result['npc_action']
        else:
            weapon_key = hit_result.get('weapon')
            if weapon_key:
                weapon_meta = entity.session.load_weapon(weapon_key)

        if not weapon_meta:
            return False

        return weapon_meta.get('type') == 'melee_attack'

    def _build_action(self, entity, target, slot_level, spell_details, hit_result):
        action = DivineSmiteAction(entity.session, entity, target, slot_level, spell_details, hit_result)
        action.as_bonus_action = True
        return action

class Paladin():
    def __init__(self, name):
        self.name = name
        self.lay_on_hands_max_pool = None
        self.divine_sence_max_count = None

    def initialize_paladin(self):
        self.spell_slots['paladin'] = self.reset_paladin_spell_slots()
        self.lay_on_hands_max_pool = self.paladin_level * 5
        self.divine_sense_max_count = 1 + self.cha_mod()
        self.lay_on_hands_count = self.lay_on_hands_max_pool
        divine_smite = DivineSmiteEffect(self)
        self.register_event_hook('on_attack_hit', divine_smite, 'on_attack_hit')

    def special_actions_for_paladin(self, session, battle):
        actions = []
        if LayOnHandsAction.can(self, battle):
            actions.append(LayOnHandsAction(session, self, 'lay_on_hands'))
        return actions
    
    def lay_on_hands(self, target, amt):
        if target is None:
            return 0

        available = getattr(self, 'lay_on_hands_count', 0)
        heal_amt = max(0, min(amt, available))
        if heal_amt <= 0:
            return 0

        self.lay_on_hands_count = max(0, available - heal_amt)
        self.event_manager.received_event({'source': self, 'target': target, 'value': heal_amt, 'event': 'lay_on_hands', 'mode': 'heal'})
        target.heal(heal_amt)
        return heal_amt

    def lay_on_hands_cure(self, target, conditions):
        if target is None or not conditions:
            return []

        available = getattr(self, 'lay_on_hands_count', 0)
        cost = 5 * len(conditions)
        if available < cost:
            return []

        statuses = getattr(target, 'statuses', [])

        def has_status(entity, status_name):
            if status_name == 'poisoned' and hasattr(entity, 'poisoned') and callable(entity.poisoned):
                if entity.poisoned():
                    return True
            return status_name in statuses

        def remove_status(status_name):
            removed = False
            if isinstance(statuses, list):
                while status_name in statuses:
                    statuses.remove(status_name)
                    removed = True
            return removed

        cured = []
        for condition in conditions:
            if condition == 'poisoned':
                previously_poisoned = has_status(target, 'poisoned')
                status_removed = remove_status('poisoned')
                if hasattr(target, 'remove_effect'):
                    target.remove_effect('poisoned')
                still_poisoned = has_status(target, 'poisoned')
                if previously_poisoned and (status_removed or not still_poisoned):
                    cured.append('poisoned')
            else:
                was_afflicted = condition in statuses
                status_removed = remove_status(condition)
                if hasattr(target, 'remove_effect'):
                    target.remove_effect(condition)
                if was_afflicted and (status_removed or condition not in statuses):
                    cured.append(condition)

        if not cured:
            return []

        self.lay_on_hands_count = max(0, available - cost)
        self.event_manager.received_event({
            'source': self,
            'target': target,
            'event': 'lay_on_hands',
            'mode': 'cure',
            'conditions': cured,
            'value': cost
        })
        return cured

    def paladin_spell_casting_modifier(self):
        return self.cha_mod()
    
    def paladin_spell_attack_modifier(self):
        return self.proficiency_bonus() + self.cha_mod()

    def short_rest_for_paladin(self, battle):
        pass
    
    def long_rest_for_paladin(self, battle):
        pass
    
    def max_slots_for_paladin(self, level):
        return PALADIN_SPELL_SLOT_TABLE[self.paladin_level - 1][level - 1] if level < len(PALADIN_SPELL_SLOT_TABLE[self.paladin_level - 1]) else 0

    def reset_paladin_spell_slots(self):
        return OrderedDict((index, slots) for index, slots in enumerate(PALADIN_SPELL_SLOT_TABLE[self.paladin_level - 1]))
