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
        super().__init__(session, source, 'spell')
        self.spell_class = spell
        self.level = 0  # base spell level
        self.at_level = 0 # cast at level
        self.casting_time = "action"
        self.spell_action = None
        self.target = None
        self.spellcasting_class = None
        # When True, ``resolve`` skips the slot/resource consumption step.
        # Used by readied spells: the slot was already consumed at ready
        # time (per RAW: "you cast it as normal but hold its energy"), so
        # releasing the held spell as a reaction must not deduct it again.
        self.skip_consume_at_resolve = False

    def __str__(self):
        name = "SpellAction: unknown"
        if self.spell_action:
            name = f"SpellAction: {self.spell_action.short_name()}"
            if self.at_level != self.level:
                name += f" upcasted at level {self.at_level}"
            if self.target:
                name += f" to {self.target}"
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
            'casting_time': self.casting_time,
            'spellcasting_class': self.spellcasting_class
        }
        if self.target:
            if isinstance(self.target, list):
                hash['target'] = [t.entity_uid for t in self.target]
            else:
                hash['target'] = self.target.entity_uid
        if hasattr(self, 'using'):
            hash['using'] = self.using
        return hash

    
    @staticmethod
    def from_dict(data):
        action = SpellAction(data['session'], data['source'], data['action_type'])
        action.level = data['level']
        action.spell_class = data['spell_class']
        action.at_level = data['at_level']
        action.casting_time = data['casting_time']
        action.target = data['target']
        action.spellcasting_class = data.get('spellcasting_class')
        if data.get('using'):
            action.using = data['using']
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

        requested_spell = opt.get("spell", None)
        if requested_spell:
            return SpellAction.can_cast(entity, battle, requested_spell)

        # Only surface the generic "spell" action if at least one spell is
        # currently castable.
        for spell_name in entity.available_spells(battle):
            if SpellAction.can_cast(entity, battle, spell_name):
                return True
        return False

    @staticmethod
    def can_cast(entity, battle, spell, at_level=None, as_scroll=False):
        if not spell:
            return True

        spell_details = entity.session.load_spell(spell)
        amt, resource = spell_details['casting_time'].split(":")
        if at_level is None:
            at_level = spell_details['level']

        slot_owner = entity.owner if entity.familiar() else entity

        if not as_scroll:
            if spell_details['level'] > 0:
                has_slot = False
                for spell_class in spell_details.get("spell_list_classes", []):
                    class_key = spell_class.lower()
                    if hasattr(slot_owner, 'next_spell_slot_level'):
                        if slot_owner.next_spell_slot_level(class_key, at_level) is not None:
                            has_slot = True
                            break
                    elif slot_owner.spell_slots_count(at_level, class_key) > 0:
                        has_slot = True
                        break

                if not has_slot:
                    return False

        if not battle:
            return True

        # If a leveled spell has already been cast this turn, do not allow any
        # further spellcasting that consumes an action/bonus action.
        if entity.casted_leveled_spells(battle) > 0 and resource in ["action", "bonus_action"]:
            return False

        if resource == "action" and entity.total_actions(battle) == 0:
            return False

        if resource == "bonus_action" and entity.total_bonus_actions(battle) == 0:
            return False

        if resource == "reaction" and not entity.has_reaction(battle):
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
            # Some call sites pass 0 to mean "cast at base level".
            action.at_level = at_level if at_level else action.level
            spell_name = spell.get("spell_class", classify(spell_name)) + "Spell"
            spell_name = spell_name.replace("Natural20::", "")
            spell_class = load_spell_class(spell_name)
            action.spell_class = spell_class
            action.spell_action = spell_class(self.session, self.source, spell_name, spell)
            action.spell_action.action = action
            slot_owner = action.source.owner if action.source.familiar() else action.source
            if action.at_level > 0 and hasattr(slot_owner, 'next_spell_slot_level'):
                for spell_class_name in spell.get('spell_list_classes', []):
                    class_key = spell_class_name.lower()
                    slot_level = slot_owner.next_spell_slot_level(class_key, action.at_level)
                    if slot_level is not None:
                        action.at_level = slot_level
                        action.spellcasting_class = class_key
                        break
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
        spell_action.spellcasting_class = self.spellcasting_class
        spell_action.skip_consume_at_resolve = getattr(self, 'skip_consume_at_resolve', False)
        if hasattr(self, 'using'):
            spell_action.using = self.using
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

        if not getattr(self, 'skip_consume_at_resolve', False):
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
        # Guard against double processing when other action types proxy to SpellAction.apply
        if item.get('_spell_action_applied'):
            return item.get('_spell_action_result')

        if battle and session is None:
            session = battle.session

        spell_apply_result = None
        for klass in SpellAction._all_spell_descendants():
            result = klass.apply(battle, item, session)
            if result is not None:
                spell_apply_result = result

        item['_spell_action_applied'] = True
        item['_spell_action_result'] = spell_apply_result

        if item['type'] == 'spell_damage':
            if item['target'].passive():
                item['target'].is_passive = False
            damage_event(item, battle)
        elif item['type'] == 'dismiss_effect':
            item['source'].dismiss_effect(item['effect'])
            session.event_manager.received_event({
                'event': 'dismiss_effect',
                'source': item['source'],
                'target': item.get('target'),
                'effect': item['effect']
            })
        elif item['type'] == 'spell_miss':
            if item['target'].passive():
                item['target'].is_passive = False
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

        return spell_apply_result

