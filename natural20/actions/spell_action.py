from dataclasses import dataclass
from natural20.utils.attack_util import damage_event
from natural20.action import Action
from natural20.spell.shocking_grasp_spell import ShockingGraspSpell
from natural20.spell.firebolt_spell import FireboltSpell
from natural20.spell.mage_armor_spell import MageArmorSpell
from natural20.spell.chill_touch_spell import ChillTouchSpell
from natural20.spell.expeditious_retreat_spell import ExpeditiousRetreatSpell
from natural20.spell.magic_missile_spell import MagicMissileSpell
from natural20.spell.ray_of_frost_spell import RayOfFrostSpell
from natural20.spell.sacred_flame_spell import SacredFlameSpell
from natural20.spell.cure_wounds_spell import CureWoundsSpell
from natural20.spell.guiding_bolt_spell import GuidingBoltSpell
from natural20.spell.shield_spell import ShieldSpell
from natural20.utils.string_utils import classify
from natural20.spell.spell import Spell
from enum import Enum
import pdb

class SpellActionConstants(Enum):
    SPELL_DAMAGE = "spell_damage"
    SPELL_MISS = "spell_miss"

@dataclass
class SpellAction(Action):
    spell_class: str
    level: int
    casting_time: str

    def __init__(self, session, source, action_type, spell=None):
        super().__init__(session, source, action_type)
        self.spell_class = spell
        self.level = 0  # base spell level
        self.at_level = 0 # cast at level
        self.casting_time = "action"
        self.spell_action = None
        self.target = None

    def __str__(self):
        name = "SpellAction: unknown"
        if self.spell_action:
            name = f"SpellAction: {self.spell_action.short_name()}"
            if self.at_level != self.level:
                name += f" upcasted at level {self.at_level}"
        return name

    def __repr__(self):
        return self.__str__()

    def short_name(self):
        if self.spell_action:
            return self.spell_action.short_name()
        return "spell"

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
    def can_cast(entity, battle, spell, at_level=None):
        if not spell:
            return True

        spell_details = battle.session.load_spell(spell)
        amt, resource = spell_details['casting_time'].split(":")
        if at_level is None:
            at_level = spell_details['level']

        if spell_details['level'] > 0:
            total_slots_count = 0
            for spell_class in spell_details.get("spell_list_classes", []):
                # check spell slots
                total_slots_count += entity.spell_slots_count(at_level, spell_class.lower())

            if total_slots_count == 0:
                return False

        if resource == "action" and entity.total_actions(battle) == 0:
            return False

        if resource == "bonus_action" and entity.total_bonus_actions(battle) == 0:
            return False

        return True

    @staticmethod
    def build(session, source):
        action = SpellAction(session, source, "spell")
        return action.build_map()

    def build_map(self):
        def select_spell(spell_choice):
            action = self.clone()
            spell_name, at_level = spell_choice
            spell = self.session.load_spell(spell_name)
            if not spell:
                raise Exception(f"spell not found {spell_name}")
            action.spell = spell
            action.level = spell.get("level", 0)
            action.at_level = at_level
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
            elif spell_name == 'MagicMissileSpell':
                spell_class = MagicMissileSpell
            elif spell_name == 'RayOfFrostSpell':
                spell_class = RayOfFrostSpell
            elif spell_name == 'ShieldSpell':
                spell_class = ShieldSpell
            elif spell_name == 'SacredFlameSpell':
                spell_class = SacredFlameSpell
            elif spell_name == 'CureWoundsSpell':
                spell_class = CureWoundsSpell
            elif spell_name == 'GuidingBoltSpell':
                spell_class = GuidingBoltSpell
            else:
                raise Exception(f"spell class not found {spell_name}")
            action.spell_class = spell_class
            action.spell_action = spell_class(self.session, self.source, spell_name, spell)
            action.spell_action.action = action
            return action.spell_action.build_map(action)

        return {
                "action": self,
                "param": [
                    {
                         "type": "select_spell"
                    }
                ],
                "next": select_spell
        }

    def clone(self):
        spell_action = SpellAction(self.session, self.source, self.action_type, self.spell_class)
        spell_action.level = self.level
        spell_action.at_level = self.at_level
        spell_action.target = self.target
        if self.spell_action:
            spell_action.spell_action = self.spell_action.clone()
            spell_action.spell_action.action = spell_action
        return spell_action

    def resolve(self, session, map=None, opts=None):
        battle = opts.get("battle")
        self.result = self.spell_action.resolve(self.source, battle, self)
        self.spell_action.consume(battle)
        return self

    def compute_hit_probability(self, battle, opts = None):
        if self.spell_action is None:
            return 0

        return self.spell_action.compute_hit_probability(battle, opts)

    def avg_damage(self, battle, opts=None):
        if self.spell_action is None:
            return 0

        return self.spell_action.avg_damage(battle, opts)

    def _all_spell_descendants():
        for klass in Spell.__subclasses__():
            if klass.__subclasses__():
                yield from klass.__subclasses__()
            else:
                yield klass

    def apply(battle, item):
        for klass in SpellAction._all_spell_descendants():
            klass.apply(battle, item)

        if item['type'] == 'spell_damage':
            damage_event(item, battle)
        elif item['type'] == 'spell_miss':
            battle.event_manager.received_event({
                'attack_roll': item['attack_roll'],
                'attack_name': item['attack_name'],
                'advantage_mod': item['advantage_mod'],
                'as_reaction': bool(item.get('as_reaction', False)),
                'adv_info': item.get('adv_info', None),
                'source': item['source'],
                'target': item['target'],
                'thrown': item.get('thrown', False),
                'event': 'miss'
            })

