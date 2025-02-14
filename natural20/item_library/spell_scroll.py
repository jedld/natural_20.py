from natural20.die_roll import DieRoll
from natural20.item_library.object import Object
from natural20.actions.spell_action import SpellAction
from natural20.utils.spell_loader import load_spell_class
from natural20.utils.string_utils import classify
from typing import Dict
from typing import Any
import pdb

class SpellScroll(Object):
    def __init__(self, name: Any, properties: Dict[str, Any]):
        super().__init__(name, properties)
        self.spell = properties['spell']
        self.level = properties['level']
        self.properties = properties

    def consumable(self):
        return True

    def can_use(self, entity, battle):
        if not entity.in_spell_list(self.spell):
            return False
        if not SpellAction.can_cast(entity, battle, self.spell, as_scroll=True):
            return False
        return True

    def available_interactions(self, entity, battle):
        available_interactions = {}
        if self.can_use(entity):
            available_interactions['use'] = 'use'
        return available_interactions

    def build_map(self, interact_action):
        session = interact_action.session
        spell = session.load_spell(self.spell)
        spell_name = spell.get("spell_class", classify(self.spell)) + "Spell"
        spell_name = spell_name.replace("Natural20::", "")
        spell_class = load_spell_class(spell_name)
        interact_action.spell_class = spell_class
        interact_action.spell_action = spell_class(session, interact_action.source, spell_name, spell)
        interact_action.spell_action.action = interact_action
        return interact_action.spell_action.build_map(interact_action)

    def resolve(self, entity, battle, action, battle_map):
        result = action.spell_action.resolve(entity, battle, action, battle_map)
        result.append({
            'source': entity,
            'spell': self.spell,
            'level': self.level,
            'type': 'use_item',
            'spell_action': action.spell_action
        })
        return result

    def use(self, entity, result, session=None):
        result['spell_action'].consume(result['battle'], as_scroll=True)
