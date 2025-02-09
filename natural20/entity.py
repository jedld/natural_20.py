from natural20.die_roll import DieRoll
import math
import pdb
from natural20.event_manager import EventManager
from natural20.evaluator.entity_state_evaluator import EntityStateEvaluator
from typing import List, Tuple
from natural20.concern.notable import Notable
import uuid
import i18n
class Entity(EntityStateEvaluator, Notable):

    ATTRIBUTE_TYPES = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']
    ATTRIBUTE_TYPES_ABBV = ['str', 'dex', 'con', 'int', 'wis', 'cha']

    ALL_SKILLS = ['acrobatics', 'animal_handling', 'arcana', 'athletics', 'deception', 'history',
                  'insight', 'intimidation', 'investigation', 'medicine', 'nature', 'perception',
                  'performance', 'persuasion', 'religion', 'sleight_of_hand', 'stealth', 'survival']

    SKILL_AND_ABILITY_MAP = {
        'dex': ['acrobatics', 'sleight_of_hand', 'stealth'],
        'wis': ['animal_handling', 'insight', 'medicine', 'perception', 'survival'],
        'int': ['arcana', 'history', 'investigation', 'nature', 'religion'],
        'con': [],
        'str': ['athletics'],
        'cha': ['deception', 'intimidation', 'performance', 'persuasion']
    }

    def __init__(self, name, description, attributes = None, event_manager = None):
        if attributes is None:
            attributes = {}
        if event_manager is None:
            event_manager = EventManager()
        self.name = name
        self._description = description
        self.attributes = attributes
        self.statuses = []
        self.ability_scores = {}
        self.entity_event_hooks = {}
        self.effects = {}
        self.grapples = []
        self.grappling = []
        self.flying = False
        self.casted_effects = []
        self.death_fails = 0
        self.death_saves = 0
        self.hidden_stealth = None
        self._temp_hp = 0
        self.event_handlers = {}
        self.event_manager = event_manager
        self.concentration = None
        self.entity_uid = uuid.uuid4()

        # Attach methods dynamically
        for ability, skills in self.SKILL_AND_ABILITY_MAP.items():
            for skill in skills:
                setattr(self, f"{skill}_mod", self.make_skill_mod_function(skill, ability))
                setattr(self, f"{skill}_check", self.make_skill_check_function(skill))

    def profile_image(self):
        return self.token_image()

    def description(self):
        return self.properties.get('description', self._description)

    def items_label(self):
      return self.t(f"entity.#{self.__class__}.item_label", default=f"{self.name} Items")

    def concentration_on(self, effect):
        if effect is None:
            raise ValueError("effect cannot be None")

        if self.concentration:
            self.dismiss_effect(self.concentration)
        self.concentration = effect

    def current_concentration(self):
        return self.concentration

    def class_descriptor(self):
        return self.name.lower()

    def class_and_level(self):
        return []

    def armor_class(self):
        return 0
    
    def equipped_ac(self):
        return self.armor_class()
    
    def any_class_feature(self, features):
        return False

    def is_npc(self):
        return False

    def object(self):
        return False

    def expertise(self, prof):
        return prof in self.properties.get('expertise', [])

    def is_two_handed_weapon(self, weapon):
        return 'versatile' in weapon.get('properties', []) and self.used_hand_slots() <= 1.0

    # Returns the proficiency bonus of this entity
    # @return [Integer]
    def proficiency_bonus(self):
        return self.properties.get('proficiency_bonus', 2)

    def make_skill_mod_function(self, skill, ability):
        def skill_mod():
            if self.is_npc() and skill in self.properties.get('skills', {}):
                return self.properties['skills'][skill]

            modifiers = getattr(self, f"{ability}_mod")()
            if self.proficient(skill):
                bonus = self.proficiency_bonus() * 2 if self.expertise(skill) else self.proficiency_bonus()
            else:
                bonus = 0
            return modifiers + bonus
        return skill_mod

    def make_skill_check_function(self, skill):
        def skill_check(battle=None, **opts):
            modifiers = getattr(self, f"{skill}_mod")()
            description = opts.get('description', f"dice roll for {skill}")
            return DieRoll.roll_with_lucky(self, f"1d20+{modifiers}", description=description, battle=battle)
        return skill_check

    def __str__(self):
        return f"{self.name}"
    
    def __repr__(self):
        return f"{self.name}"
    
    def name(self):
        return self.name
    
    def hp(self):
        return self.attributes["hp"]
    
    def temp_hp(self):
        return self._temp_hp

    # Returns the character hit die
    # @return [dict]
    def hit_die(self):
        return self._current_hit_die
    
    def darkvision(self, distance):
        if not self.properties.get('darkvision'):
            return False
        adjusted_darkvision_distance = self.properties.get('darkvision')
        if adjusted_darkvision_distance < distance:
            return False
        return True
    

    def label(self):
        return i18n.t(self.name)

    def token_image(self):
        return self.properties.get('token_image') or f"token_{(self.properties.get('kind') or self.properties.get('sub_type') or self.properties.get('name')).lower()}.png"

    def token_size(self):
        square_size = self.size()

        if square_size == 'tiny':
            return 1
        elif square_size == 'small':
            return 1
        elif square_size == 'medium':
            return 1
        elif square_size == 'large':
            return 2
        elif square_size == 'huge':
            return 3
        else:
            raise ValueError(f"invalid size {square_size}")

    def size_identifier(self):
        square_size = self.size()
        if square_size == 'tiny':
            return 0
        elif square_size == 'small':
            return 1
        elif square_size == 'medium':
            return 2
        elif square_size == 'large':
            return 3
        elif square_size == 'huge':
            return 4
        elif square_size == 'gargantuan':
            return 5
        else:
            raise ValueError(f"invalid size {square_size}")
        
    def languages(self):
        return self.properties.get('languages', [])
        
    def long_jump_distance(self):
        return self.ability_scores.get('str')

    def passive_perception(self):
        return self.properties.get('passive_perception', 10 + self.wis_mod())

    def passive_insight(self):
        return self.properties.get('passive_insight', 10 + self.wis_mod())
    
    def passive_investigation(self):
        return self.properties.get('passive_investigation', 10 + self.int_mod())

    def perception_check(self, battle):
        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return 0

        return DieRoll.roll(f"1d20+{self.wis_mod()}", description="perception check", entity=self, battle=battle)

    def drop_grapple(self):
        for target in self.grappling:
            self.ungrapple(target)

    def dead(self):
        return 'dead' in self.statuses

    def undead(self):
        return 'undead' in self.properties.get('race', [])

    def race(self):
        race = self.properties.get('race', [])
        return " ".join(race)

    def add_casted_effect(self, effect):
        if effect not in self.casted_effects:
            self.casted_effects.append(effect)

    def has_spell_effect(self, spell):
        active_effects = [effect for effects in self.effects.values() for effect in effects if not effect.get('expiration') or effect.get('expiration') > self.session.game_time]
        return any(effect['effect'].id == spell for effect in active_effects)


    def register_effect(self, effect_type, handler, method_name=None, effect=None, source=None, duration=None):
        if effect_type not in self.effects:
            self.effects[effect_type] = []
        effect_descriptor = {
            'handler': handler,
            'method': method_name if method_name is not None else effect_type,
            'effect': effect,
            'source': source
        }
        if duration is not None:
            effect_descriptor['expiration'] = self.session.game_time + int(duration)
        self.effects[effect_type].append(effect_descriptor)

    def register_event_hook(self, event_type, handler, method_name=None, source=None, effect=None, duration=None):
        if event_type not in self.entity_event_hooks:
            self.entity_event_hooks[event_type] = []
        event_hook_descriptor = {
            'handler': handler,
            'method': method_name if method_name is not None else event_type,
            'effect': effect,
            'source': source
        }
        if duration is not None:
            event_hook_descriptor['expiration'] = self.session.game_time + int(duration)
        self.entity_event_hooks[event_type].append(event_hook_descriptor)

    def ability_mod(self, type):
        mod_type = {
            'wisdom': 'wis',
            'dexterity': 'dex',
            'constitution': 'con',
            'intelligence': 'int',
            'charisma': 'cha',
            'strength': 'str'
        }.get(type, None)
        if mod_type:
            return self.modifier_table(self.ability_scores.get(mod_type))
        else:
            return None

    # Checks if an item is equipped
    # @param item_name [String,Symbol]
    # @return [Boolean]
    def equipped(self, item_name):
        return item_name in [item['name'] for item in self.equipped_items()]
    
    # Equips an item
    # @param item_name [String,Symbol]
    def equip(self, item_name, ignore_inventory=False):
        self.properties['equipped'] = self.properties.get('equipped', [])
        if ignore_inventory:
            self.properties['equipped'].append(str(item_name))
            self.resolve_trigger('equip')
            return
        item = self.deduct_item(item_name)
        if item:
            self.properties['equipped'].append(str(item_name))
            self.resolve_trigger('equip')

    def make_dead(self):
        if not self.dead():
            self.event_manager.received_event({ 'source': self, 'event': 'died' })
            # print(f"{self.name} died. :(")
            self.drop_grapple()
            if 'dead' not in self.statuses:
                self.statuses.append('dead')
            self.do_prone()

            if 'stable' in self.statuses:
                self.statuses.remove('stable')
            if 'unconscious' in self.statuses:
                self.statuses.remove('unconscious')

            # dismiss all effects
            for effect in self.casted_effects:
                self.dismiss_effect(effect['effect'])

    def make_unconscious(self):
        if not self.unconscious() and not self.dead():
            self.drop_grapple()
            self.event_manager.received_event({ 'source': self, 'event': 'unconscious' })
            # print(f"{self.name} is unconscious.")

            self.do_prone()
            self.statuses.append('unconscious')


    def lockpick(self, battle=None):
        proficiency_mod = self.dex_mod()
        if self.proficient("thieves_tools"):
            bonus = self.proficiency_bonus() * 2 if self.expertise("thieves_tools") else self.proficiency_bonus()
        else:
            bonus = 0
        proficiency_mod += bonus
        return DieRoll.roll_with_lucky(self, "1d20+{proficiency_mod}",
                            description=self.t('dice_roll.thieves_tools'),
                            battle=battle)

    def saving_throw_mod(self, save_type):
        modifier = self.ability_mod(save_type)
        if modifier is None:
            return 0
        modifier += self.proficiency_bonus() if self.proficient(f"{save_type}_save") else 0
        return modifier

    def saving_throw(self, save_type, battle=None):
        modifier = self.saving_throw_mod(save_type)
        op = '+' if modifier >= 0 else ''
        disadvantage = True if save_type in ['dex', 'str'] and not self.proficient_with_equipped_armor() else False

        if self.unconscious():
            return DieRoll.roll("1", description=f"dice_roll.{save_type}_saving_throw")

        return DieRoll.roll(f"d20{op}{modifier}", disadvantage=disadvantage, battle=battle, entity=self,
                            description=f"dice_roll.{save_type}_saving_throw")

    def short_rest(self, battle, prompt=False):
        controller = battle.controller_for(self)

        # hit die management
        if prompt and controller and hasattr(controller, 'prompt_hit_die_roll'):
            while sum(self._current_hit_die.values()) > 0:
                ans = controller.prompt_hit_die_roll(self, [k for k, v in self._current_hit_die.items() if v > 0])

                if ans == 'skip':
                    break
                else:
                    self.use_hit_die(ans, battle=battle)
        else:
            while self.hp() < self.max_hp():
                available_die = [die for die, num in self._current_hit_die.items() if num > 0]
                available_die.sort()

                if not available_die:
                    break

                old_hp = self.hp

                self.use_hit_die(available_die[0], battle=battle)

                if self.hp == old_hp:
                    break

        if self.unconscious() and self.stable():
            self.heal(1)

    def use_hit_die(self, die_type, battle=None):
        if die_type in self._current_hit_die and self._current_hit_die[die_type] > 0:
            self._current_hit_die[die_type] -= 1
            hit_die_roll = DieRoll.roll(f"d{die_type}", battle=battle, entity=self, description="hit die")
            self.event_manager.received_event({'source': self, 'event': 'hit_die', 'roll': hit_die_roll})
            self.heal(hit_die_roll.result())

    def grappled(self):
        return 'grappled' in self.statuses
    
    def do_grapple(self, target):
        self.grappling.append(target)

    def is_grappling(self):
        return len(self.grappling) > 0

    def grappling_targets(self):
        return self.grappling

    # @param target [Natural20::Entity]
    def ungrapple(self, target):
        self.grappling.remove(target)
        if  self in target.grapples:
            target.grapples.remove(self)
        if len(target.grapples)==0 and 'grappled' in target.statuses:
            target.statuses.remove('grappled')


    def unconscious(self):
        return not self.dead() and 'unconscious' in self.statuses
    
    def conscious(self):
        return not self.dead() and not self.unconscious()
    
    def stand(self):
        self.statuses.remove('prone')

    def standing_jump_distance(self):
        return int(self.ability_scores.get('str') / 2)
    
    def resistant_to(self, damage_type):
        return damage_type in self.resistances
    
    def disengage(self, battle):
        entity_state = battle.entity_state_for(self)
        if entity_state and 'disengage' in entity_state.get('statuses', []):
            return True
        return False
    
    def do_disengage(self, battle):
        entity_state = battle.entity_state_for(self)
        entity_state['statuses'].add('disengage')

    def has_reaction(self, battle):
        return battle.entity_state_for(self).get('reaction', 0) > 0

    def has_action(self, battle):
        if not battle:
            return True

        return battle.entity_state_for(self).get('action', 0) > 0
    def hidden(self):
        return 'hidden' in self.statuses
    
    def unsqueeze(self):
        if 'squeezed' in self.statuses:
            self.statuses.remove('squeezed')

    def preception_check(self, battle):
        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return 0

        return entity_state.get('active_perception', 0)
    
    def grapple(self, target):
        if not hasattr(self, 'grappling'):
            self.grappling = []
        self.grappling.append(target)

    def is_flying(self):
        return bool(self.flying)
    
    def fly(self):
        if self.properties.get('speed_fly'):
            self.flying = True 
    
    def can_fly(self):
        return self.properties.get('speed_fly')
    
    def melee_distance(self):
        return 0
    
    def entered_melee(self, map, entity, pos_x, pos_y):
        entity_1_sq = map.entity_squares(self)
        entity_2_sq = map.entity_squares_at_pos(entity, pos_x, pos_y)

        for entity_1_pos in entity_1_sq:
            for entity_2_pos in entity_2_sq:
                cur_x, cur_y = entity_1_pos
                pos_x, pos_y = entity_2_pos

                distance = math.floor(math.sqrt((cur_x - pos_x)**2 + (cur_y - pos_y)**2) * map.feet_per_grid) # one square - 5 ft

                # determine melee options
                if distance <= self.melee_distance() + 2.5:
                    return True

        return False
    
    def hand_slots_required(self, item):
        if item['type'] == 'armor':
            return 0.0
        elif item['light']:
            return 0.5
        elif item['two_handed']:
            return 2.0
        else:
            return 1.0

    def used_hand_slots(self, weapon_only=False):
        equipped_items = [item for item in self.equipped_items() if item['subtype'] == 'weapon' or (not weapon_only and item['type'] == 'shield')]
        hand_slots = sum(self.hand_slots_required(item) for item in equipped_items)

        return hand_slots
    
    @property
    def damage_vulnerabilities(self):
        return self.properties.get('damage_vulnerabilities', [])

    def vulnerable_to(self, damage_type):
        return damage_type in self.damage_vulnerabilities

    
    def initiative_bonus(self):
        return self.dex_mod()

    def initiative(self, battle=None):
        roll = DieRoll.roll_with_lucky(self, f"1d20+{self.initiative_bonus()}", description="initiative", battle=battle)
        value = float(roll.result()) + self.ability_scores.get('dex') / 100.0
        if battle:
            battle.event_manager.received_event({ "source": self,
                                     "event": "initiative",
                                     "roll": roll,
                                     "value" : value})
        else:
            self.event_manager.received_event({ "source": self,
                                        "event": "initiative",
                                        "roll": roll,
                                        "value" : value})
        return value

    def str_mod(self):
        return self.modifier_table(self.ability_scores.get('str'))

    def con_mod(self):
        return self.modifier_table(self.ability_scores.get('con'))

    def wis_mod(self):
        return self.modifier_table(self.ability_scores.get('wis'))

    def cha_mod(self):
        return self.modifier_table(self.ability_scores.get('cha'))

    def int_mod(self):
        return self.modifier_table(self.ability_scores.get('int'))

    def dex_mod(self):
        return self.modifier_table(self.ability_scores.get('dex'))
    
    def ability_score_dex(self):
        return self.ability_scores.get('dex')
    
    def ability_score_str(self):
        return self.ability_scores.get('str')

    def ability_score_con(self):
        return self.ability_scores.get('con')

    def ability_score_int(self):
        return self.ability_scores.get('int')

    def ability_score_wis(self):
        return self.ability_scores.get('wis')

    def ability_score_cha(self):
        return self.ability_scores.get('cha')
    
    def casted_leveled_spells(self, battle=None):
        if battle:
            return len(battle.entity_state_for(self).get('casted_level_spells', [])) > 0
        return False

    def modifier_table(self, value):
        mod_table = [[0, 1, -5],
                     [1, 1, -5],
                     [2, 3, -4],
                     [4, 5, -3],
                     [6, 7, -2],
                     [8, 9, -1],
                     [10, 11, 0],
                     [12, 13, 1],
                     [14, 15, 2],
                     [16, 17, 3],
                     [18, 19, 4],
                     [20, 21, 5],
                     [22, 23, 6],
                     [24, 25, 7],
                     [26, 27, 8],
                     [28, 29, 9],
                     [30, 30, 10]]

        for low, high, mod in mod_table:
            if value is None:
                raise ValueError(f"invalid value {value}")
            if low <= value <= high:
                return mod
        return None

    def dismiss_effect(self, effect):
        if self.concentration == effect:
            self.concentration = None

        dismiss_count = 0
        if effect.action.target:
            if isinstance(effect.action.target,list):
                for target in effect.action.target:
                    dismiss_count += target.remove_effect(effect)
            else:
                dismiss_count = effect.action.target.remove_effect(effect)

        dismiss_count += self.remove_effect(effect)
        return dismiss_count

    def remove_effect(self, effect):
        if effect.source:
            effect.source.casted_effects = [f for f in effect.source.casted_effects if f['effect'].id != effect.id]

        dismiss_count = 0

        new_effects = {}
        for key, value in self.effects.items():
            delete_effects = [f for f in value if f['effect'].id == effect.id]
            dismiss_count += len(delete_effects)
            new_effects[key] = [f for f in value if f not in delete_effects]
        self.effects = new_effects
        
        new_entity_event_hooks = {}
        for key, value in self.entity_event_hooks.items():
            delete_hooks = [f for f in value if f['effect'] == effect]
            dismiss_count += len(delete_hooks)
            new_entity_event_hooks[key] = [f for f in value if f not in delete_hooks]
        self.entity_event_hooks = new_entity_event_hooks
        return dismiss_count
    
    def wearing_armor(self):
        return any(item['type'] in ['armor', 'shield'] for item in self.equipped_items())
    
    def reset_turn(self, battle):
        entity_state = battle.entity_state_for(self)
        if not entity_state:
            raise ValueError("entity has not been added to the battle yet")

        entity_state.update({
            'action': 1,
            'bonus_action': 1,
            'reaction': 1,
            'movement': self.speed(),
            'free_object_interaction': 1,
            'active_perception': 0,
            'active_perception_disadvantage': 0,
            'two_weapon': None,
            'action_surge': None,
            'casted_level_spells': [],
            'positions_entered': {}
        })

        if 'dodge' in entity_state['statuses']:
            entity_state['statuses'].remove('dodge')

        if 'disengage' in entity_state['statuses']:
            entity_state['statuses'].remove('disengage')

        battle.dismiss_help_actions_for(self)
        battle.event_manager.received_event({'source': self, 'event': 'start_of_turn'})
        self.resolve_trigger('start_of_turn')
        self._cleanup_effects()

        if not self.class_feature("multiattack"):
            return entity_state

        multiattack_groups = {}
        for a in self.properties["actions"]:
            if a.get("multiattack_group"):
                group = a["multiattack_group"]
                multiattack_groups.setdefault(group, []).append(a["name"])

        entity_state["multiattack"] = multiattack_groups

        return entity_state

    def resolve_trigger(self, event_type, opts=None):
        if opts is None:
            opts = {}
        if event_type in self.entity_event_hooks:
            available_hooks = [effect for effect in self.entity_event_hooks[event_type] if not effect.get('expiration') or effect['expiration'] > self.session.game_time]
            if len(available_hooks) == 0:
                return

            active_hook = available_hooks[-1]
            if active_hook:
                getattr(active_hook['handler'], active_hook['method'])(self, {**opts, 'effect': active_hook['effect']})

    def do_grappled_by(self, grappler):
        if 'grappled' not in self.statuses:
            self.statuses.append('grappled')
        if grappler not in self.grapples:
            self.grapples.append(grappler)
        return grappler.do_grapple(self)

    def grappled_by(self, grappler) -> bool:
        if self.grappled():
            return False
        return grappler in self.grapples

    def escape_grapple_from(self, grappler):
        if grappler in self.grapples:
            self.grapples.remove(grappler)
        if len(self.grapples) == 0:
            self.statuses.remove('grappled')
        grappler.ungrapple(self)

    def _cleanup_effects(self):
        for _, value in self.effects.items():
            delete_effects = [f for f in value if f.get('expiration') and f['expiration'] <= self.session.game_time]
            for effect in delete_effects:
                self.dismiss_effect(effect)

        self.entity_event_hooks = {k: [f for f in value if not f.get('expiration') or f['expiration'] > self.session.game_time] for k, value in self.entity_event_hooks.items()}

        delete_casted_effects = [f for f in self.casted_effects if f.get('expiration') and f['expiration'] <= self.session.game_time]
        for effect in delete_casted_effects:
            self.dismiss_effect(effect['effect'])


    # Checks if an entity still has an action available
    # @param battle [Natural20::Battle]
    def action(self, battle=None):
        if battle is None:
            return True

        return (battle.entity_state_for(self).get('action', 0) > 0)

    def total_actions(self, battle):
        if battle:
            if not battle.entity_state_for(self):
                return 0

            return battle.entity_state_for(self).get('action')
        else:
            return 1

    def total_reactions(self, battle):
        if battle:
            return battle.entity_state_for(self).get('reaction')
        else:
            return 1

    def free_object_interaction(self, battle):
        if battle is None:
            return True

        return (battle.entity_state_for(self).get('free_object_interaction', 0) > 0)

    def total_bonus_actions(self, battle):
        return battle.entity_state_for(self).get('bonus_action')

    def available_movement(self, battle):
        if battle is None:
            return self.speed()

        if self.grappled() or self.unconscious():
            return 0

        return battle.entity_state_for(self).get('movement')

    def available_spells(self):
        return []
    
    def familiar(self):
      return self.properties.get('familiar')
    
    def speed(self):
        c_speed = self.properties.get('speed_fly',0) if self.is_flying() else self.properties['speed']

        if self.has_effect('speed_override'):
            c_speed = self.eval_effect('speed_override', { "stacked": True, "value" : c_speed})

        return c_speed
    

    def stable(self):
        return 'stable' in self.statuses
    
    def prone(self):
        return 'prone' in self.statuses
    
    def do_prone(self):
        if 'prone' not in self.statuses:
            self.statuses.append('prone')

    # Hides the entity in battle with a specified stealth value
    # @param battle [Natural20::Battle]
    # @param stealth [Integer]
    def do_hide(self, stealth):
        if stealth is None:
            raise ValueError("stealth cannot be None")
        if 'hidden' not in self.statuses:
            self.statuses.append('hidden')
        self.hidden_stealth = stealth

    def squeezed(self):
        return 'squeezed' in self.statuses
    
    def do_dodge(self, battle):
        entity_state = battle.entity_state_for(self)
        entity_state['statuses'].add('dodge')

    def incapacitated(self):
        return 'incapacitated' in self.statuses or 'unconscious' in self.statuses or \
            'sleep' in self.statuses or 'dead' in self.statuses

    def dodge(self, battle):
        if not battle:
            return False

        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return False

        return 'dodge' in entity_state.get('statuses', [])
    
    def break_stealth(self):
        if 'hidden' in self.statuses:
            self.statuses.remove('hidden')
        self.hidden_stealth = None

    # @param map [Natural20::BattleMap]
    def push_from(self, map, pos_x, pos_y, distance=5):
        x, y = map.entity_or_object_pos(self)
        effective_token_size = self.token_size() - 1
        ofs_x, ofs_y = 0, 0

        if pos_x in range(x, x + effective_token_size + 1) and pos_y not in range(y, y + effective_token_size + 1):
            ofs_y = distance if pos_y < y else -distance
        elif pos_y in range(y, y + effective_token_size + 1) and pos_x not in range(x, x + effective_token_size + 1):
            ofs_x = distance if pos_x < x else -distance
        elif [pos_x, pos_y] == [x - 1, y - 1]:
            ofs_x = distance
            ofs_y = distance
        elif [pos_x, pos_y] == [x + effective_token_size + 1, y - 1]:
            ofs_x = -distance
            ofs_y = distance
        elif [pos_x, pos_y] == [x - 1, y + effective_token_size + 1]:
            ofs_x = distance
            ofs_y = -distance
        elif [pos_x, pos_y] == [x + effective_token_size + 1, y + effective_token_size + 1]:
            ofs_x = -distance
            ofs_y = -distance
        else:
            raise ValueError(f"Invalid source position {pos_x}, {pos_y}")

        # convert to squares
        ofs_x //= map.feet_per_grid
        ofs_y //= map.feet_per_grid

        new_x = x + ofs_x
        new_y = y + ofs_y

        if map.placeable(self, new_x, new_y):
            return new_x, new_y
        else:
            return None

    def trigger_event(self, event_name, battle, session, map, event):
        if event_name in self.event_handlers:
            callback = self.event_handlers[event_name]
            event['trigger'] = event_name
            return callback(battle, session, self, map, event)

    def npc(self):
        return False

    def has_effect(self, effect_type):
        if effect_type not in self.effects:
            return False
        if not self.effects[effect_type]:
            return False

        active_effects = [effect for effect in self.effects[effect_type] if not effect.get('expiration') or effect['expiration'] > self.session.game_time]

        return bool(active_effects)

    # @param map [Natural20::BattleMap]
    # @param target_position [Array<Integer,Integer>]
    # @param adjacent_only [Boolean] If false uses melee distance otherwise uses fixed 1 square away
    def melee_squares(self, map, target_position=None, adjacent_only=False, squeeze=False) -> List[Tuple[int, int]]:
        result = []
        if adjacent_only:
            cur_x, cur_y = target_position or map.entity_or_object_pos(self)
            entity_squares = map.entity_squares_at_pos(self, cur_x, cur_y, squeeze)
            for sq in entity_squares:
                for x_off in range(-1, 2):
                    for y_off in range(-1, 2):
                        if x_off == 0 and y_off == 0:
                            continue

                        # adjust melee position based on token size
                        adjusted_x_off = x_off
                        adjusted_y_off = y_off

                        position = (sq[0] + adjusted_x_off, sq[1] + adjusted_y_off)

                        if (position in entity_squares) or (position in result) or (position[0] < 0) or (position[0] >= map.size[0]) or (position[1] < 0) or (position[1] >= map.size[1]):
                            continue

                        result.append(position)
        else:
            step = self.melee_distance() // map.feet_per_grid
            cur_x, cur_y = target_position or map.entity_or_object_pos(self)
            for x_off in range(-step, step+1):
                for y_off in range(-step, step+1):
                    if x_off == 0 and y_off == 0:
                        continue

                    # adjust melee position based on token size
                    adjusted_x_off = x_off
                    adjusted_y_off = y_off

                    if x_off < 0:
                        adjusted_x_off -= self.token_size() - 1
                    if y_off < 0:
                        adjusted_y_off -= self.token_size() - 1

                    position = (cur_x + adjusted_x_off, cur_y + adjusted_y_off)

                    if (position[0] < 0) or (position[0] >= map.size[0]) or (position[1] < 0) or (position[1] >= map.size[1]):
                        continue

                    result.append(position)
        return result
    
    # Retrieves the item count of an item in the entity's inventory
    # @param inventory_type [str]
    # @return [int]
    def item_count(self, inventory_type):
        if inventory_type not in self.inventory:
            return 0
        return self.inventory[inventory_type]['qty']
    
    def attack_roll_mod(self, weapon):
        modifier = self.attack_ability_mod(weapon)

        if self.proficient_with_weapon(weapon):
            modifier += self.proficiency_bonus()

        return modifier


    def attack_ability_mod(self, weapon):
        modifier = 0

        if weapon['type'] == 'melee_attack':
            weapon_properties = weapon.get('properties', [])
            if weapon_properties is None:
                weapon_properties = []
            if 'finesse' in weapon_properties:
                modifier = max(self.str_mod(), self.dex_mod())
            else:
                modifier = self.str_mod()
        elif weapon['type'] == 'ranged_attack':
            if self.class_feature('archery'):
                modifier = self.dex_mod() + 2
            else:
                modifier = self.dex_mod()

        return modifier

    def proficient_with_weapon(self, weapon):
        if isinstance(weapon, str):
            weapon = self.session.load_thing(weapon)

        if weapon['name'] == 'Unarmed Attack':
            return True

        proficiency_types = self.properties.get('weapon_proficiencies', [])
        for prof in proficiency_types:
            if weapon['proficiency_type'] and (prof in weapon['proficiency_type'] or prof == weapon['name'].replace(" ", "_")):
                return True

        return False

    def equipped_items(self):
        equipped_arr = self.properties.get('equipped', [])
        equipped_list = []
        for k in equipped_arr:
            item = self.session.load_thing(k)
            if not item:
                raise Exception(f"unknown item {k}")
            equipped_list.append(self._to_item(k, item))

        return equipped_list
    
    def unequipped_items(self):
        inventory = self.inventory
        unequipped_list = []
        for k in inventory.keys():
            item = self.session.load_thing(k)
            if not item.get('equippable', False):
                continue

            if not item:
                raise Exception(f"unknown item {k}")
            item_info = self._to_item(k, item)
            item_info['qty'] = inventory[k]['qty']
            unequipped_list.append(item_info)

        return unequipped_list
    
    def equipped_armor(self):
        return [item for item in self.equipped_items() if item['type'] in ['armor', 'shield']]
    
    def is_familiar(self):
        return self.properties.get('familiar')

    def proficient_with_equipped_armor(self):
        shields_and_armor = self.equipped_armor()
        if len(shields_and_armor) == 0:
            return True

        for item in shields_and_armor:
            if not self.proficient_with_armor(item['name']):
                print(f"not proficient with {item['name']}")
                return False

        return True

    def save_throw(self, save_type, battle, opts=None):
        """
        Perform a saving throw for the entity
        """
        if opts is None:
            opts = {}

        modifier = self.ability_mod(save_type)
        if modifier is None:
            raise ValueError(f"invalid ability {save_type}")

        modifier += self.proficiency_bonus() if self.proficient(f"{save_type}_save") else 0
        op = '+' if modifier >= 0 else ''
        disadvantage = True if save_type in ['dex', 'str'] and not self.proficient_with_equipped_armor() else False
        save_roll = DieRoll.roll(f"d20{op}{modifier}", disadvantage=disadvantage, battle=battle, entity=self,
                            description=f"dice_roll.{save_type}_saving_throw")

        if self.has_effect('bless'):
            save_roll += DieRoll.roll("1d4", description="bless", entity=self, battle=battle)
        return save_roll

    def skills(self):
        return self.properties.get('skills', [])
    
    def proficient(self, prof):
        return (prof in self.properties.get('skills', []) or
                prof in self.properties.get('tools', []) or
                prof in self.properties.get('weapon_proficiencies', []) or
                prof in [f"{p}_save" for p in self.properties.get('saving_throw_proficiencies', [])])

    def proficient_with_armor(self, item):
        armor = self.session.load_thing(item)
        if not armor:
            raise Exception(f"unknown item {item}")
        if armor['type'] not in ['armor', 'shield']:
            raise Exception(f"not armor {item}")

        if armor['type'] == 'armor':
            return self.proficient(f"{armor['subtype']}_armor")
        
        elif armor['type'] == 'shield':
            return self.proficient('shields')

        return False

    def _to_item(self, k, item):
        return {
            'name': k,
            'ac' : item.get('ac', None),
            'description': item.get('description', None),
            'bonus_ac' : item.get('bonus_ac', None),
            'damage' : item.get('damage', None),
            'damage_2' : item.get('damage_2', None),
            'damage_type' : item.get('damage_type', None),
            'range' : item.get('range', None),
            'range_max' : item.get('range_max', None),
            'label': item.get('label', str(item.get('name')).capitalize()),
            'type': item.get('type'),
            'subtype': item.get('subtype'),
            'light': item.get('properties') and 'light' in item.get('properties', []),
            'two_handed': item.get('properties') and 'two_handed' in item.get('properties', []),
            'light_properties': item.get('light'),
            'proficiency_type': item.get('proficiency_type'),
            'metallic': bool(item.get('metallic')),
            'properties': item.get('properties'),
            'qty': 1,
            'equipped': True,
            'weight': item.get('weight')
        }
    # Removes Item from inventory
    # @param ammo_type [str]
    # @param amount [int]
    # @return [dict]
    def deduct_item(self, ammo_type, amount=1):
        if ammo_type not in self.inventory:
            return None

        qty = self.inventory[ammo_type]['qty']
        self.inventory[ammo_type]['qty'] = max(qty - amount, 0)
        if self.inventory[ammo_type]['qty'] == 0:
            return self.inventory.pop(ammo_type)
        return self.inventory[ammo_type]
    
    # Removes an item from the inventory
    # @param ammo_type [Symbol,String]
    # @param amount [Integer]
    # @return [Hash]
    def remove_item(self, ammo_type, amount=1):
        return self.deduct_item(ammo_type, amount)


    # Adds an item to your inventory
    # @param ammo_type [Symbol,String]
    # @param amount [Integer]
    # @param source_item [Object]
    def add_item(self, ammo_type, amount=1, source_item=None):
        if ammo_type not in self.inventory:
            self.inventory[ammo_type] = {
                'qty': 0,
                'type': source_item.type if source_item else ammo_type
            }

        qty = self.inventory[ammo_type].get('qty', 1)
        self.inventory[ammo_type]['qty'] = qty + amount

    def ranged_spell_attack(self, battle, spell, advantage=False, disadvantage=False):
        spell_classes = spell.get('spell_list_classes', [])
        class_types = spell_classes if spell_classes else ['wizard']
        attack_modifers = [self.spell_attack_modifier(class_type=class_type.lower()) for class_type in class_types]
        return DieRoll.roll(f"1d20+{max(attack_modifers)}", description=f"Ranged Spell Attack: {spell['name']}", entity=self, battle=battle, advantage=advantage, disadvantage=disadvantage)

    def melee_spell_attack(self, battle, spell, advantage=False, disadvantage=False):
        spell_classes = spell.get('spell_list_classes', [])
        class_types = spell_classes if spell_classes else ['wizard']
        attack_modifers = [self.spell_attack_modifier(class_type=class_type.lower()) for class_type in class_types]
        return DieRoll.roll(f"1d20+{max(attack_modifers)}", description=f"Melee Spell Attack: {spell['name']}", entity=self, battle=battle, advantage=advantage, disadvantage=disadvantage)

    def multiattack(self, battle, npc_action):
        if not npc_action:
            return False
        if not self.class_feature("multiattack"):
            return False

        entity_state = battle.entity_state_for(self)

        if not entity_state.get("multiattack", False):
            return False
        if not npc_action.get("multiattack_group", False):
            return False

        for _, attacks in entity_state["multiattack"].items():
            if npc_action["name"] in attacks:
                return True

        return False

    # Unequips a weapon
    # @param item_name [String,Symbol]
    # @param transfer_inventory [Boolean] Add this item to the inventory?
    def unequip(self, item_name, transfer_inventory=True):
        if item_name in self.properties['equipped']:
            self.properties['equipped'].remove(item_name)
            if transfer_inventory:
                self.add_item(item_name)

    def spell_save_dc(self, ability_type='intelligence'):
        return 8 + self.proficiency_bonus() + self.ability_mod(ability_type)

    def spell_attack_modifier(self, class_type='wizard'):
        method_name = f"{class_type.lower()}_spell_attack_modifier"
        if hasattr(self, method_name):
            return getattr(self, method_name)()

        return 0

    # Returns the available spells for the current user
    # @param battle [Natural20::Battle]
    # @return [Dict]
    def spell_list(self, battle):
        prepared_spells = self.prepared_spells()
        spell_list = {}
        for spell in prepared_spells:
            details = self.session.load_spell(spell)
            if not details:
                continue

            qty, resource = details['casting_time'].split(':')

            disable_reason = []
            if resource == 'action' and battle and battle.ongoing() and self.total_actions(battle) == 0:
                disable_reason.append('no_action')
            if resource == 'reaction':
                disable_reason.append('reaction_only')

            if resource == 'bonus_action' and battle and battle.ongoing() and self.total_bonus_actions(battle) == 0:
                disable_reason.append('no_bonus_action')
            elif resource == 'hour' and battle.ongoing():
                disable_reason.append('in_battle')
            if details['level'] > 0:
                slot_count = 0
                for spell_class_type in details.get('spell_list_classes', []):
                    slot_count += self.spell_slots_count(details['level'], spell_class_type.lower())

                if slot_count == 0:
                    disable_reason.append('no_spell_slot')

            spell_list[spell] = details.copy()
            spell_list[spell]['disabled'] = disable_reason

        return spell_list

    def equipped_npc_weapons(self, session=None):
        return [item['name'] for item in self.equipped_items() if item["subtype"] == 'weapon']

    def take_damage(self, dmg: int, battle=None, damage_type='piercing', \
                    critical=False, roll_info=None, sneak_attack=None):
        self.attributes["hp"] -= dmg
        instant_death = False
        if self.unconscious():
            if 'stable' in self.statuses:
                self.statuses.remove('stable')
            self.death_fails += 2 if critical else 1

            complete = False
            if self.death_fails >= 3:
                complete = True
                self.make_dead()
                self.death_saves = 0
                self.death_fails = 0
            if battle:
                battle.event_manager.received_event({'source': self, 'event': 'death_fail', 'saves': self.death_saves,
                                                    'fails': self.death_fails, 'complete': complete})

        if self.hp() < 0 and abs(self.hp()) >= self.properties['max_hp']:
            instant_death = True
            self.make_dead()
            if battle and self.familiar():
                battle.remove(self)
        elif self.hp() <= 0:
            self.make_dead() if self.npc() else self.make_unconscious()
            # drop concentration spells
            if self.concentration:
                self.dismiss_effect(self.concentration)

            if battle and self.familiar():
                battle.remove(self)
        elif self.hp() > 0:
            if self.concentration:
                # make a concentration check
                concentration_check = self.save_throw('constitution', battle)
                diffculty_class = max([10, dmg // 2])
                if concentration_check.result() < diffculty_class:
                    self.event_manager.received_event({'source': self,
                                                       'event': 'concentration_check',
                                                       'result': 'failure',
                                                       'effect' : self.concentration,
                                                       'roll': concentration_check,
                                                       'dc': diffculty_class
                                        })
                    self.dismiss_effect(self.concentration)
                else:
                    self.event_manager.received_event({'source': self,
                                                       'event': 'concentration_check',
                                                       'result': 'success',
                                                       'effect' : self.concentration,
                                                       'roll': concentration_check,
                                                       'dc': diffculty_class
                                        })

        if self.hp() <= 0:
            self.attributes["hp"] = 0

        if battle:
            battle.event_manager.received_event({'source': self, 'event': 'damage', 'value': dmg, 'roll_info': roll_info, 'instant_death': instant_death, 'sneak_attack': sneak_attack})

    def on_take_damage(self, battle, _damage_params):
        controller = battle.controller_for(self)
        if controller and hasattr(controller, 'attack_listener'):
            controller.attack_listener(battle, self)

    def current_effects(self):
        active_effects = []
        for _, value in self.effects.items():
            for effect in value:
                if not effect.get('expiration') or effect['expiration'] > self.session.game_time:
                    active_effects.append(effect)
        return active_effects

    def eval_effect(self, effect_type, opts=None):
        if not opts:
            opts = {}

        if not self.has_effect(effect_type):
            return None

        active_effects = [effect for effect in self.effects[effect_type] if not effect.get('expiration') or effect['expiration'] > self.session.game_time]

        if not opts.get('stacked'):
            active_effects = [active_effects[-1]] if active_effects else []

        if active_effects:
            result = opts.get('value')
            for active_effect in active_effects:
                opts.update( { "effect": active_effect['effect'], "value" : result })
                result = getattr(active_effect['handler'], active_effect['method'])(self, opts)
            return result

        return None
    
    def make_stable(self):
        if 'stable' not in self.statuses:
            self.statuses.append("stable")
        self.death_fails = 0
        self.death_saves = 0


    def make_conscious(self):
        if 'unconscious' in self.statuses:
            self.statuses.remove("unconscious")
        if 'stable' in self.statuses:
            self.statuses.remove("stable")

    def heal(self, amt):
        if self.dead():
            return

        if self.has_effect("heal_override"):
            amt = self.eval_effect("heal_override", {"heal": amt})

        prev_hp = self.hp()

        self.attributes["hp"] = min(self.max_hp(), self.hp() + amt)

        if self.hp() > 0 and amt > 0:
            self.death_saves = 0
            self.death_fails = 0
            if self.unconscious():
                print(f"{self.name} is now conscious because of healing and has {self.hp()} hp")
                self.make_conscious()
            self.event_manager.received_event({'source': self, 'event': 'heal', 'previous': prev_hp, 'new': self.hp, 'value': amt})


    def light_properties(self):
        if not self.equipped_items():
            return None

        bright = [0]
        dim = [0]

        for item in self.equipped_items():
            if not item.get('light_properties'):
                continue

            bright.append(item['light_properties'].get('bright', 0))
            dim.append(item['light_properties'].get('dim', 0))

        bright = max(bright)
        dim = max(dim)

        if dim <= 0 and bright <= 0:
            return None

        return {'dim': dim, 'bright': bright}
    
    def death_saving_throw(self, battle=None):
        roll = DieRoll.roll_with_lucky(self, '1d20', description='dice_roll.death_saving_throw', battle=battle)
        if roll.nat_20():
            self.make_conscious()
            self.heal(1)
            # print(f"{self.name} rolled a natural 20 on a death saving throw and is now conscious with 1 hp")
            self.event_manager.received_event({'source': self, 'event': 'death_save', 'roll': roll, 'saves': self.death_saves,
                                                    'fails': self.death_fails, 'complete': True, 'stable': True, 'success': True})
        elif roll.result() >= 10:
            self.death_saves += 1
            complete = False
            # print(f"{self.name} succeeded a death saving throw ({self.death_saves}/3)")
            if self.death_saves >= 3:
                complete = True
                self.death_saves = 0
                self.death_fails = 0
                self.make_stable()
                # print(f"{self.name} is now stable")
            self.event_manager.received_event({'source': self, 'event': 'death_save', 'roll': roll, 'saves': self.death_saves,
                                                    'fails': self.death_fails, 'complete': complete, 'stable': complete})
        else:
            if roll.nat_1():
                # print(f"{self.name} rolled a natural 1 on a death saving throw :(")
                self.death_fails += 2 
            else:
                self.death_fails += 1

            complete = False
            if self.death_fails >= 3:
                complete = True
                self.make_dead()
                self.death_saves = 0
                self.death_fails = 0
                # print(f"{self.name} failed the final death saving throw and died")

            self.event_manager.received_event({'source': self, 'event': 'death_fail', 'roll': roll, 'saves': self.death_saves,
                                                   'fails': self.death_fails, 'complete': complete})


    def attach_handler(self, event_name, callback):
        self.event_handlers[event_name] = callback

    def usable_items(self):
        usable = []
        for k, v in self.inventory.items():
            item_details = self.session.load_equipment(k)

            if not item_details or not item_details.get('usable', False):
                continue
            if item_details['consumable'] and v['qty'] == 0:
                continue

            usable.append({
                'name': str(k),
                'label': item_details.get('name', k),
                'item': item_details,
                'qty': v['qty'],
                'consumable': item_details['consumable']
            })
        return usable

    def other_items(self):
        other = []
        for k, v in self.inventory.items():
            item_details = self.session.load_equipment(k)
            if not item_details or item_details.get('usable', False):
                continue
            other.append({
                'name': str(k),
                'label': item_details.get('name', k),
                'item': item_details,
                'qty': v['qty']
            })
        return other

    def has_spells(self):
        if not self.properties.get('prepared_spells', None):
            return False
        return len(self.properties['prepared_spells']) > 0

    def has_item(self, item_name):
        if item_name in self.inventory:
            return True
        if item_name in self.equipped_items():
            return True
        return False

    # Returns items in the "backpack" of the entity
    # @return [List]
    def inventory_items(self, session):
        items = []
        for k, v in self.inventory.items():
            item = session.load_thing(k)
            if item is None:
                raise Exception(f"unable to load unknown item {k}")
            if v['qty'] > 0:
                items.append({
                    'name': k,
                    'label': v['label'] if v.get('label',None) else str(k),
                    'qty': v['qty'],
                    'equipped': False,
                    'weight': item.get('weight', None)
                })
        return items
    
    # Returns the weight of all items in the inventory in lbs
    # @return [float] weight in lbs
    def inventory_weight(self, session):
        total_weight = 0.0
        for item in self.inventory_items(session) + self.equipped_items():
            weight = float(item['weight']) if item.get('weight', None) else 0.0
            total_weight += weight * item['qty']
        return total_weight
    
    def dexterity_check(self, bonus=0, battle=None, description=None):
        disadvantage = not self.proficient_with_equipped_armor() if battle is None else False
        return DieRoll.roll_with_lucky(self, f"1d20+{self.dex_mod() + bonus}", disadvantage=disadvantage, description=description or 'dice_roll.dexterity', battle=battle)

    def perception_proficient(self):
        return self.proficient('perception')

    def investigation_proficient(self):
        return self.proficient('investigation')

    def insight_proficient(self):
        return self.proficient('insight')

    def stealth_proficient(self):
        return self.proficient('stealth')

    def acrobatics_proficient(self):
        return self.proficient('acrobatics')

    def athletics_proficient(self):
        return self.proficient('athletics')

    def medicine_proficient(self):
        return self.proficient('medicine')
    
    # removes all equipped. Used for tests
    def unequip_all(self):
        self.properties['equipped'].clear()

    # Checks if item can be equipped
    # @param item_name [String,Symbol]
    # @return [str]
    def check_equip(self, item_name):
        weapon = self.session.load_thing(item_name)
        if weapon and weapon.get('subtype') == 'weapon' or weapon['type'] in ['shield', 'armor']:
            hand_slots = self.used_hand_slots() + self.hand_slots_required(self._to_item(item_name, weapon))
            armor_slots = len([item for item in self.equipped_items() if item['type'] == 'armor'])
            if hand_slots > 2.0:
                return 'hands_full'
            elif armor_slots >= 1 and weapon['type'] == 'armor':
                return 'armor_equipped'
            else:
                return 'ok'
        else:
            return 'unequippable'
  
    # Returns the carrying capacity of an entity in lbs
    # @return [float] carrying capacity in lbs
    def carry_capacity(self):
        return self.ability_scores.get('str', 1) * 15.0

    def to_dict(self):
        return {
            'name': self.name,
            'properties': self.properties,
            'attributes': self.attributes,
            'inventory': self.inventory,
            'effects': self.effects,
            'status': self.statuses,
            'death_saves': self.death_saves,
            'death_fails': self.death_fails,
            'concentration': self.concentration,
            'casted_effects': self.casted_effects,
            'grapples': self.grapples,
            'temp_hp' : self._temp_hp
        }

    def long_rest(self):
        self.attributes['hp'] = self.properties['max_hp']
        self.death_saves = 0
        self.death_fails = 0
        self.statuses.clear()
        self.casted_effects.clear()
        self.grapples.clear()
        self.concentration = None
        self._temp_hp = 0
        self.resolve_trigger('long_rest')

    def t(self, key, **kwargs):
        return self.session.t(key, kwargs)