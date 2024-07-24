from abc import ABC, abstractmethod
from typing import Callable
from dataclasses import dataclass
from natural20.utils.attack_util import damage_event
from natural20.action import Action
from natural20.spell.shocking_grasp_spell import ShockingGraspSpell
from natural20.spell.firebolt_spell import FireboltSpell
from natural20.spell.mage_armor_spell import MageArmorSpell
from natural20.spell.chill_touch_spell import ChillTouchSpell
from natural20.spell.expeditious_retreat_spell import ExpeditiousRetreatSpell
from natural20.utils.string_utils import classify
from natural20.spell.spell import Spell
from natural20.utils.spell_attack_util import consume_resource
from enum import Enum

class SpellAction(Enum):
    SPELL_DAMAGE = "spell_damage"
    SPELL_MISS = "spell_miss"

@dataclass
class SpellAction(Action):
    spell_class: str
    level: int
    casting_time: str

    def __init__(self, session, source, spell):
        super().__init__(session, source, spell)

    @staticmethod
    def can(entity, battle, opt = None):
        if not entity.has_spells():
            return False

        if battle is None or not battle.ongoing():
            return True

        if opt is None:
            opt = {}
        return SpellAction.can_cast(entity, battle, opt.get("spell", None))

    @staticmethod
    def can_cast(entity, battle, spell):
        if not spell:
            return True

        spell_details = battle.session.load_spell(spell)
        amt, resource = spell_details.casting_time.split(":")

        if resource == "action" and battle.total_actions(entity) > 0:
            return True

        return False

    @staticmethod
    def build(session, source):
        action = SpellAction(session, source, "spell")
        return action.build_map()

    def build_map(self):
        def select_spell(spell_choice):
            spell_name, at_level = spell_choice
            spell = self.session.load_spell(spell_name)
            if not spell:
                raise Exception(f"spell not found {spell_name}")
            self.spell = spell
            self.at_level = at_level
            spell_name = spell.get("spell_class", classify(spell_name)) + "Spell"
            spell_name = spell_name.replace("Natural20::", "")
            if spell_name == 'ShockingGraspSpell':
                spell_class = ShockingGraspSpell
            elif spell_name == 'FireboltSpell':
                spell_class = FireboltSpell
            elif spell_name == 'MageArmorSpell':
                spell_class = MageArmorSpell
            elif spell_name == 'ChillTouchSpell':
                spell_class = ChillTouchSpell
            elif spell_name == 'ExpeditiousRetreatSpell':
                spell_class = ExpeditiousRetreatSpell
            else:
                raise Exception(f"spell class not found {spell_name}")
            self.spell_action = spell_class(self.session, self.source, spell, self.spell)
            self.spell_action.action = self
            return self.spell_action.build_map(self)

        return {
                "action": self,
                "param": [
                    {
                         "type": "select_spell"
                    }
                ],
                "next": select_spell
        }

    def resolve(self, session, map=None, opts=None):
        battle = opts.get("battle")
        self.result = self.spell_action.resolve(self.source, battle, self)
        return self

    def apply(battle, item):
        for klass in Spell.__subclasses__():
            klass.apply(battle, item)
        if item['type'] == 'spell_damage':
            damage_event(item, battle)
            consume_resource(battle, item)
        elif item['type'] == 'spell_miss':
            consume_resource(battle, item)
            battle.event_manager.received_event({
                'attack_roll': item['attack_roll'],
                'attack_name': item['attack_name'],
                'advantage_mod': item['advantage_mod'],
                'as_reaction': bool(item['as_reaction']),
                'adv_info': item['adv_info'],
                'source': item['source'],
                'target': item['target'],
                'event': 'miss'
            })

