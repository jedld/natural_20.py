from dataclasses import dataclass
from natural20.utils.attack_util import damage_event
from natural20.action import Action
from natural20.utils.spell_loader import load_spell_class
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
    
    def to_dict(self):
        hash = {
            'session': self.session,
            'source': self.source.entity_uid,
            'action_type': self.action_type,
            'spell_class': self.spell_class,
            'level': self.level,
            'at_level': self.at_level,
            'casting_time': self.casting_time
        }
        if self.target:
            if isinstance(self.target, list):
                hash['target'] = [t.entity_uid for t in self.target]
            else:
                hash['target'] = self.target.entity_uid
        return hash

    
    @staticmethod
    def from_dict(data):
        action = SpellAction(data['session'], data['source'], data['action_type'])
        action.level = data['level']
        action.spell_class = data['spell_class']
        action.at_level = data['at_level']
        action.casting_time = data['casting_time']
        action.target = data['target']
        return action

    def short_name(self):
        if self.spell_action:
            return self.spell_action.short_name()
        return "spell"

    @staticmethod
    def can(entity, battle, opt = None):
        if not entity.has_spells() and not entity.familiar():
            return False

        if entity.familiar() and not entity.owner.has_spells():
            return False

        if battle is None or not battle.ongoing():
            return True

        if entity.familiar() and not entity.has_reaction(battle):
            return False

        if opt is None:
            opt = {}

        return SpellAction.can_cast(entity, battle, opt.get("spell", None))

    @staticmethod
    def can_cast(entity, battle, spell, at_level=None, as_scroll=False):
        if not spell:
            return True

        spell_details = entity.session.load_spell(spell)
        amt, resource = spell_details['casting_time'].split(":")
        if at_level is None:
            at_level = spell_details['level']

        if not as_scroll:
            if spell_details['level'] > 0:
                total_slots_count = 0
                for spell_class in spell_details.get("spell_list_classes", []):
                    # check spell slots
                    total_slots_count += entity.spell_slots_count(at_level, spell_class.lower())

                if total_slots_count == 0:
                    return False

        if not battle:
            return True

        # check if the entity has the required resources to cast the spell
        if entity.casted_leveled_spells(battle) > 0 \
            and resource in ["action", "bonus_action"] \
            and at_level > 0:
            return False

        if resource == "action" and entity.total_actions(battle) == 0:
            return False

        if resource == "bonus_action" and entity.total_bonus_actions(battle) == 0:
            return False

        return True

    def validate(self, battle_map, target=None):
        if target is None:
            target = self.target

        self.spell_action.validate(battle_map, target)
        self.errors = self.spell_action.errors

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
            spell_class = load_spell_class(spell_name)
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
        if opts is None:
            opts = {}
        battle = opts.get("battle", None)
        self.result = self.spell_action.resolve(self.source, battle, self, map)

        for r in self.result:
            if r.get('attack_roll',None) is not None:
                self.source.break_stealth()

        if 'verbal' in self.spell_action.properties.get('components', []):
            self.source.break_stealth()

        self.spell_action.consume(battle)

        return self

    def compute_advantage_info(self, battle, opts=None):
        if self.spell_action is None:
            return None

        return self.spell_action.compute_advantage_info(battle, opts)

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

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        for klass in SpellAction._all_spell_descendants():
            klass.apply(battle, item, session)

        if item['type'] == 'spell_damage':
            damage_event(item, battle)
        elif item['type'] == 'spell_miss':
            session.event_manager.received_event({
                'attack_roll': item.get('attack_roll', None),
                'attack_name': item['attack_name'],
                'advantage_mod': item.get('advantage_mod', None),
                'as_reaction': bool(item.get('as_reaction', False)),
                'adv_info': item.get('adv_info', None),
                'source': item['source'],
                'target': item['target'],
                'thrown': item.get('thrown', False),
                'spell_save': item.get('spell_save', None),
                'dc': item.get('dc', None),
                'event': 'miss'
            })

