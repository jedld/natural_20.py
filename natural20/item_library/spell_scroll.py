from natural20.die_roll import DieRoll
from natural20.item_library.object import Object
from natural20.actions.spell_action import SpellAction
from natural20.actions.use_item_action import UseItemAction
from natural20.utils.spell_loader import load_spell_class
from natural20.utils.string_utils import classify
from typing import Dict
from typing import Any

class SpellScroll(Object):
    def __init__(self, map: Any, properties: Dict[str, Any]):
        super().__init__(map, properties)
        self.spell = properties['spell']
        self.level = properties['level']
        self.properties = properties

    def consumable(self):
        return True
    
    def can_use(self, entity):
        if entity.in_spell_list(self.spell):
            return True
        return False
    
    def available_interactions(self, entity, battle):
        available_interactions = {}
        if self.can_use(entity):
            available_interactions['use'] = 'use'
        return available_interactions
    
    def build_map(self, interact_action: UseItemAction):
        spell = self.session.load_spell(self.spell)
        spell_name = spell.get("spell_class", classify(spell_name)) + "Spell"
        spell_name = spell_name.replace("Natural20::", "")
        spell_class = load_spell_class(spell_name)
        interact_action.spell_class = spell_class
        interact_action.spell_action = spell_class(self.session, self.source, spell_name, spell)
        interact_action.spell_action.action = interact_action
        interact_action.spell_action = interact_action
        return interact_action.spell_action.build_map(interact_action)

    def resolve(self, entity, battle, action):
        result = action.spell_action.resolve(self.source, battle, self)
        result['spell_action'] = action.spell_action
        return result
    
    def use(self, entity, result, session=None):
        if result.get('attack_roll',None) is not None:
          entity.break_stealth()
        action = result['spell_action']

        if 'verbal' in action.spell_action.properties.get('components', []):
            action.source.break_stealth()
        
        action.spell_action.consume(action.battle)
