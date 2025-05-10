from natural20.actions.lay_on_hands_action import LayOnHandsAction
# from natural20.effect import Effect
from collections import OrderedDict
import pdb

PALADIN_SPELL_SLOT_TABLE = [
        [3, 2],
        [3, 3],
        [3, 3],
        [4, 2],
        [4, 2],
        [4, 3],
        [4, 3],
        [4, 3, 2],
        [4, 3, 2],
        [4, 3, 3],
        [4, 3, 3],
        [4, 3, 3, 1],
        [4, 3, 3, 1],
        [4, 3, 3, 2],
        [4, 3, 3, 2],
        [4, 3, 3, 3, 1],
        [4, 3, 3, 3, 1],
        [4, 3, 3, 3, 2],
        [4, 3, 3, 3, 2]
    ]

class Effect:
    def __init__(self, source, target, value):
        self.source = source
        self.target = target
        self.value = value

    def on_attack_hit(self, result):
        pass

    def dismiss_effect(self):
        pass

class DivineSmiteEffect(Effect):
    def __init__(self, source, target, value):
        super().__init__(source, target, value)
        self.value = value

    def on_attack_hit(self, result):
        pdb.set_trace()

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
        divine_smite = DivineSmiteEffect(self, self, self.paladin_level)
        self.register_event_hook('on_attack_hit', divine_smite, 'on_attack_hit')

    def special_actions_for_paladin(self, session, battle):
        actions = []
        if LayOnHandsAction.can(self, battle):
            actions.append(LayOnHandsAction(session, self, 'lay_on_hands'))
        return actions
    
    def lay_on_hands(self, target, amt):
        self.event_manager.received_event({'source': self, 'target': target, 'value': amt, 'event': 'lay_on_hands'})
        target.heal(amt)

    def paladin_spell_casting_modifier(self):
        return self.cha_mod()
    
    def paladin_spell_attack_modifier(self):
        return self.proficiency_bonus() + self.cha_mod()

    def short_rest_for_paladin(self, battle):
        pass
    
    def long_rest_for_paladin(self, battle):
        pass
    
    def reset_paladin_spell_slots(self):
        return OrderedDict((index, slots) for index, slots in enumerate(PALADIN_SPELL_SLOT_TABLE[self.paladin_level - 1]))
