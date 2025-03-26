from natural20.entity import Entity
from natural20.die_roll import DieRoll
from natural20.entity_class.fighter import Fighter
from natural20.entity_class.rogue import Rogue
from natural20.entity_class.wizard import Wizard
from natural20.entity_class.cleric import Cleric
from natural20.actions.action_surge_action import ActionSurgeAction
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction
from natural20.actions.look_action import LookAction
from natural20.actions.move_action import MoveAction
from natural20.actions.dodge_action import DodgeAction
from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.hide_action import HideAction, HideBonusAction
from natural20.actions.disengage_action import DisengageAction, DisengageBonusAction
from natural20.actions.dash import DashAction, DashBonusAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.grapple_action import GrappleAction, DropGrappleAction
from natural20.actions.escape_grapple_action import EscapeGrappleAction
from natural20.actions.stand_action import StandAction
from natural20.actions.prone_action import ProneAction
from natural20.actions.shove_action import ShoveAction
from natural20.actions.help_action import HelpAction
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.ground_interact_action import GroundInteractAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.interact_action import InteractAction
from natural20.utils.action_builder import autobuild
from natural20.concern.container import Container
from natural20.utils.movement import compute_actual_moves
from natural20.concern.lootable import Lootable
from natural20.concern.inventory import Inventory
import yaml
import os
import copy
import uuid
import pdb


class PlayerCharacter(Entity, Fighter, Rogue, Wizard, Cleric, Lootable, Inventory):
  ACTION_LIST = [
    SpellAction,
    AttackAction,
    HideAction,
    HideBonusAction,
    DashAction,
    DashBonusAction,
    DisengageAction,
    DisengageBonusAction,
    DodgeAction,
    MoveAction,
    ProneAction,
    SecondWindAction,
    StandAction,
    TwoWeaponAttackAction,
    HelpAction,
    GroundInteractAction,
    GrappleAction,
    DropGrappleAction,
    EscapeGrappleAction,
    ActionSurgeAction,
    ShoveAction,
    FirstAidAction,
    UseItemAction,
    InteractAction,
    LookAction
  ]

  def __init__(self, session, properties, name=None):
    super(PlayerCharacter, self).__init__(name, f"PC {name}", attributes={}, event_manager=session.event_manager)
    self.properties = properties

    if name is None:
      self.name = self.properties['name']

    self.display_name = self.properties.get('display_name', self.name)
    
    race_file = self.properties['race']
    self.session = session
    self.equipped = self.properties.get('equipped', [])

    self.group = self.properties.get('group', 'a')

    # use ordered dict to maintain order of spell slots
    self.spell_slots = {}
    with open(f"{self.session.root_path}/races/{race_file}.yml") as file:
      self.race_properties = yaml.safe_load(file)


    self.ability_scores = self.properties.get('ability', {})
    self.load_inventory()
    self.class_properties = {}
    self._current_hit_die = {}
    self.max_hit_die = {}
    self.resistances = self.properties.get("resistances", [])
    self.entity_uid =  self.properties.get('entity_uid', str(uuid.uuid4()))

    for klass, level in self.properties.get('classes', {}).items():
      setattr(self, f"{klass}_level", level)
      getattr(self, f"initialize_{klass}")()
      with open(f"{self.session.root_path}/char_classes/{klass}.yml") as file:
        character_class_properties = yaml.safe_load(file)
      self.max_hit_die[klass] = level

      hit_die_details = DieRoll.parse(character_class_properties['hit_die'])
      self._current_hit_die[int(hit_die_details.die_type)] = level
      self.class_properties[klass] = character_class_properties

    self.attributes["hp"] = copy.deepcopy(self.max_hp())

  def description(self):
    return super().description()

  def class_descriptor(self):
    class_level = []
    for klass, level in self.properties.get('classes', {}).items():
      class_level.append(f"{klass}-{level}")
    return "_".join(class_level).lower()
  
  def class_and_level(self):
    class_level = []
    for klass, level in self.properties.get('classes', {}).items():
      class_level.append((klass, level))
    return class_level

  @staticmethod
  def load(session, path, override=None):
    if override is None:
      override = {}

    if not path.endswith('.yml'):
      path = f"{path}.yml"

    with open(os.path.join(session.root_path, path), 'r') as file:
      properties = yaml.safe_load(file)
    properties.update(override)
    return PlayerCharacter(session, properties)
  
  def label(self):
    return self.display_name

  def level(self):
      return self.properties['level']

  def size(self):
      return self.properties.get("size") or self.race_properties.get('size')
  
  def token(self):
      return self.properties.get('token',['P'])
  
  def subrace(self):
      return self.properties['subrace']
  
  def speed(self):
    effective_speed = self.race_properties.get('subrace', {}).get(self.subrace(), {}).get('base_speed') or self.race_properties.get('base_speed')

    if self.has_effect('speed_override'):
      effective_speed = self.eval_effect('speed_override', { "stacked": True, "value" : effective_speed})

    return effective_speed

  def max_hp(self):
    _max_hp = 0
    if self.class_feature('dwarven_toughness'):
      _max_hp = self.properties['max_hp'] + self.level
    else:
      _max_hp = self.properties['max_hp']
    if self.has_effect('hit_point_max_override'):
      return self.eval_effect('hit_point_max_override', { "max_hp" : _max_hp})

    return _max_hp

  def melee_distance(self):
    if not self.properties.get('equipped', None):
      return 5

    max_range = 5
    for item in self.properties['equipped']:
      weapon_detail = self.session.load_weapon(item)
      if weapon_detail is None:
        continue
      if weapon_detail['type'] == 'melee_attack':
        max_range = max(max_range, weapon_detail['range'])

    return max_range


  def armor_class(self):
    current_ac = self.equipped_ac()
    if self.has_effect('ac_override'):
      current_ac = self.eval_effect('ac_override', { "armor_class" : self.equipped_ac() })
  
    if self.has_effect('ac_bonus'):
      current_ac += self.eval_effect('ac_bonus')

    return current_ac

  def c_class(self):
    return self.properties['classes']
  
  def available_actions(self, session, battle, opportunity_attack=False, auto_target=True, map=None, **opts):
    if opts is None:
      opts = {}

    interact_only = opts.get('interact_only', False)
    except_interact = opts.get('except_interact', False)

    if self.unconscious():
      return []
    
    if battle and battle.current_turn() != self and not opportunity_attack:
      return []

    if opportunity_attack:
      if AttackAction.can(self, battle, { 'opportunity_attack': True }):
        return self._player_character_attack_actions(session, battle, opportunity_attack=True)
      else:
        return []

    action_list = []
    if map is None:
      map = battle.map_for(self)

    for action_type in self.ACTION_LIST:
      if interact_only and action_type != InteractAction:
        continue

      if except_interact and action_type == InteractAction:
        continue

      if action_type.can(self, battle):
        if action_type == LookAction:
          action_list.append(LookAction(session, self, 'look'))
        elif action_type == AttackAction:
          action_list = action_list + self._player_character_attack_actions(session, battle, auto_target=auto_target)
        elif action_type == TwoWeaponAttackAction:
          action_list = action_list + self._player_character_attack_actions(session, battle, second_weapon=True, auto_target=auto_target)
        elif action_type == DodgeAction:
          action_list.append(DodgeAction(session, self, 'dodge'))
        elif action_type == DisengageAction:
          action_list.append(DisengageAction(session, self, 'disengage'))
        elif action_type == SecondWindAction:
          action_list.append(SecondWindAction(session, self, 'second_wind'))
        elif action_type == FirstAidAction:
          action_list.append(FirstAidAction(session, self, 'first_aid'))
        elif action_type == ActionSurgeAction:
          action_list.append(ActionSurgeAction(session, self, 'action_surge'))
        elif action_type == HideAction:
          action_list.append(HideAction(session, self, 'hide'))
        elif action_type == HideBonusAction:
          action_list.append(HideBonusAction(session, self, 'hide_bonus'))
        elif action_type == DashBonusAction:
          action = DashBonusAction(session, self, 'dash_bonus')
          action.as_bonus_action = True
          action_list.append(action)
        elif action_type == DashAction:
          action = DashAction(session, self, 'dash')
          action_list.append(action)
        elif action_type == HelpAction:
          action_list.append(HelpAction(session, self, 'help'))
        elif action_type == MoveAction:
          if not battle or not auto_target:
            action_list.append(MoveAction(session, self, 'move'))
            continue

          # no map? we skip, must be a theater of the mind mode
          if map is None:
            continue

          cur_x, cur_y = map.position_of(self)
          for x_pos in range(-1, 2):
            for y_pos in range(-1, 2):
              if x_pos == 0 and y_pos == 0:
                continue
              if map.bidirectionally_passable(self, cur_x + x_pos, cur_y + y_pos, (cur_x, cur_y), battle, allow_squeeze=False) and map.placeable(self, cur_x + x_pos, cur_y + y_pos, battle, squeeze=False):
                chosen_path = [[cur_x, cur_y], [cur_x + x_pos, cur_y + y_pos]]
                actual_movement = compute_actual_moves(self, chosen_path, map, battle, self.available_movement(battle) // 5)
                if len(actual_movement.movement) > 1 and actual_movement.impediment is None:
                  # print(f"Adding move action {actual_movement.movement}")
                  move_action = MoveAction(session, self, 'move')
                  move_action.move_path = actual_movement.movement
                  action_list.append(move_action)
        elif action_type == ProneAction:
          action = ProneAction(session, self, 'prone')
          action_list.append(action)
        elif action_type == StandAction:
          action = StandAction(session, self, 'stand')
          action_list.append(action)
        elif action_type == DisengageBonusAction:
          action = DisengageBonusAction(session, self, 'disengage_bonus')
          action_list.append(action)
        elif action_type == ShoveAction:
          action = ShoveAction(session, self, 'shove')
          action_list.append(action)
        elif action_type == GrappleAction:
          action = GrappleAction(session, self, 'grapple')
          action_list.append(action)
        elif action_type == EscapeGrappleAction:
          action = EscapeGrappleAction(session, self, 'escape_grapple')
          action_list.append(action)
        elif action_type == SpellAction:
          if auto_target:
            action_list = action_list + autobuild(self.session, SpellAction, self, battle)
          else:
            action_list.append(SpellAction(session, self, 'spell'))
        elif action_type == UseItemAction:
          if auto_target:
            action_list = action_list +  autobuild(self.session, UseItemAction, self, battle)
          else:
            action_list.append(UseItemAction(session, self, 'use_item'))
        elif action_type == InteractAction:
          if map:
            for objects in map.objects_near(self, battle):
              for interaction, details in objects.available_interactions(self).items():
                action = InteractAction(session, self, 'interact', { "target": objects,
                                                                              "object_action": [interaction, details] })
                if details.get('disabled'):
                  action.disabled = True
                  action.disabled_reason = self.t(details['disabled_text'])

                action_list.append(action)
    return action_list

  def equipped_weapons(self, session, valid_weapon_types=['ranged_attack', 'melee_attack']):
    weapon_attacks = []
    for item in self.properties.get('equipped', []):
      weapon_detail = session.load_weapon(item)
      if weapon_detail is None:
        continue
      if weapon_detail['type'] not in valid_weapon_types:
        continue
      if 'ammo' in weapon_detail and not self.item_count(weapon_detail['ammo']) > 0:
        continue
      weapon_attacks.append(item)

    return weapon_attacks

  def _player_character_attack_actions(self, session, battle, opportunity_attack=False, second_weapon=False, auto_target=True):
    # check all equipped and create attack for each
    valid_weapon_types = ['melee_attack'] if opportunity_attack else ['ranged_attack', 'melee_attack']

    weapon_attacks = []

    for item in self.properties.get('equipped', []):
      weapon_detail = session.load_weapon(item)
      if weapon_detail is None:
        continue
      if weapon_detail['type'] not in valid_weapon_types:
        continue
      if 'ammo' in weapon_detail and not self.item_count(weapon_detail['ammo']) > 0:
        continue

      attack_class = AttackAction
      attack_type = 'attack'

      if second_weapon:
        if 'light' in weapon_detail.get('properties', []) and weapon_detail['type'] == 'melee_attack' and TwoWeaponAttackAction.can(self, battle, { 'weapon': item }):
          attack_class = TwoWeaponAttackAction
          attack_type = 'two_weapon_attack'
        else:
          continue

      action = attack_class(session, self, attack_type)
      action.using = item
      weapon_attacks.append(action)

      if not opportunity_attack and weapon_detail.get('properties') and 'thrown' in weapon_detail.get('properties', []):
        action = attack_class(session, self, attack_type)
        action.using = item
        action.thrown = True
        weapon_attacks.append(action)

    if not second_weapon:
      unarmed_attack = AttackAction(session, self, 'attack')
      unarmed_attack.using = 'unarmed_attack'
      weapon_attacks.append(unarmed_attack)

    # assign possible attack targets
    if battle and auto_target:
      final_attack_list = []
      for action in weapon_attacks:
        valid_targets = battle.valid_targets_for(self, action, target_types=["enemies"])
        for target in valid_targets:
          targeted_action = copy.copy(action)
          targeted_action.target = target
          final_attack_list.append(targeted_action)
    else:
      final_attack_list = weapon_attacks
    return final_attack_list

  def placeable(self):
    if not self.dead():
      return False
    return True

  def prepared_spells(self):
    return self.properties.get('cantrips', []) + self.properties.get('prepared_spells', [])

  # Consumes a character's spell slot
  def consume_spell_slot(self, level, character_class=None, qty=1):
    if character_class is None:
      character_class = list(self.spell_slots.keys())[0]
    if self.spell_slots[character_class][level]:
      self.spell_slots[character_class][level] = max(self.spell_slots[character_class][level] - qty, 0)

  def class_feature(self, feature):
    if feature in self.properties.get('class_features', []):
      return True
    if feature in self.properties.get('attributes', []):
      return True
    if feature in self.race_properties.get('race_features', []):
      return True
    if self.subrace() and feature in self.race_properties.get('subrace', {}).get(self.subrace(), {}).get('class_features', []):
      return True
    if self.subrace() and feature in self.race_properties.get('subrace', {}).get(self.subrace(), {}).get('race_features', []):
      return True

    for properties in self.class_properties.values():
      if feature in properties.get('class_features', []):
        return True

      progression = properties.get('progression', {})
      for level in range(1, self.level() + 1):
        h_features = progression.get(f"level_{level}", { "class_features": [] }).get('class_features', [])
        if feature in  h_features:
          return True

    return False

  def proficient_with_weapon(self, weapon):
    if isinstance(weapon, str):
      weapon = self.session.load_thing(weapon)

    all_weapon_proficiencies = self.weapon_proficiencies()

    if weapon['name'].lower() in all_weapon_proficiencies:
      return True

    proficiency_type = weapon.get('proficiency_type', [])

    # if weapon in DnD 5e does not list any required proficiency, then it is considered a simple weapon
    if len(proficiency_type) == 0:
      return True

    return any(prof in proficiency_type for prof in all_weapon_proficiencies)

  def weapon_proficiencies(self):
    all_weapon_proficiencies = []
    for p in self.class_properties.values():
      if 'weapon_proficiencies' in p:
        all_weapon_proficiencies += p['weapon_proficiencies']
    all_weapon_proficiencies += self.properties.get('weapon_proficiencies', [])
    all_weapon_proficiencies += self.race_properties.get('weapon_proficiencies', [])

    subrace = self.subrace()
    if subrace:
      all_weapon_proficiencies += self.race_properties.get('subrace', {}).get(subrace, {}).get('weapon_proficiencies', [])
    return all_weapon_proficiencies


  def _proficiency_bonus_table(self):
    return [2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6]
  

  def proficiency_bonus(self):
    return self._proficiency_bonus_table()[self.level() - 1]
  
  def proficient(self, prof):
    if any(prof in c.get('proficiencies', []) for c in self.class_properties.values()):
      return True
    if any(prof in [f"{f}_save" for f in c.get('saving_throw_proficiencies', [])] for c in self.class_properties.values()):
      return True
    if self.race_properties.get('skills') and prof in self.race_properties['skills']:
      return True
    if prof in self.weapon_proficiencies():
      return True

    return super().proficient(prof)

  def equipped_ac(self):
    with open(os.path.join(self.session.root_path, 'items', 'equipment.yml')) as file:
      equipments = yaml.safe_load(file)
    equipped_meta = [equipments[e] for e in self.equipped if e in equipments]
    armor = next((equipment for equipment in equipped_meta if equipment['type'] == 'armor'), None)
    shield = next((equipment for equipment in equipped_meta if equipment['type'] == 'shield'), None)

    armor_ac = 10 + self.dex_mod() if armor is None else armor['ac'] + min(self.dex_mod(), armor['mod_cap'] if 'mod_cap' in armor else self.dex_mod()) + (1 if self.class_feature('defense') else 0)

    return armor_ac + (0 if shield is None else shield['bonus_ac'])

  def any_class_feature(self, features):
    return any(self.class_feature(f) for f in features)
  
  def darkvision(self, distance):
    if super().darkvision(distance):
      return True

    return bool(self.race_properties.get('darkvision', None) and (self.race_properties['darkvision'] >= distance))

  def spell_slots_count(self, level, character_class=None):
    if character_class is None:
      character_class = list(self.spell_slots.keys())
      total_slots = 0
      for klass in character_class:
        if self.spell_slots[klass].get(level, 0) > 0:
          total_slots += self.spell_slots[klass][level]
      return total_slots
    elif character_class not in self.spell_slots:
      return 0

    return self.spell_slots[character_class].get(level, 0)


  # Returns the number of spell slots
  # @param level [Integer]
  # @return [Integer]
  def max_spell_slots(self, level, character_class=None):
    if character_class is None:
      character_class = list(self.spell_slots.keys())[0]

    if hasattr(self, f"max_slots_for_{character_class}"):
      return getattr(self, f"max_slots_for_{character_class}")(level)

    return 0
  
  def available_spells(self, battle):
    spell_list = self.spell_list(battle)
    return [k for k, v in spell_list.items() if not v['disabled']]
  
  def available_spells_per_level(self, battle):
    spell_list = self.spell_list(battle)
    spell_per_level = [[],[],[],[],[],[],[],[],[]]
    for spell, details in spell_list.items():
      spell_per_level[details['level']].append((spell, details))

    return enumerate(spell_per_level)

  def languages(self):
    class_languages = []
    for prop in self.class_properties.values():
      class_languages += prop.get('languages', [])

    racial_languages = self.race_properties.get('languages', [])

    return sorted(super().languages() + class_languages + racial_languages)
  
  def passive_investigation(self):
    return 10 + self.int_mod() + self.investigation_proficiency()

  def passive_insight(self):
    return 10 + self.wis_mod() + self.insight_proficiency()
  
  def passive_perception(self):
    return 10 + self.wis_mod() + self.perception_proficiency()
  
  def investigation_proficiency(self):
    return self.proficiency_bonus() if self.investigation_proficient() else 0
  
  def insight_proficiency(self):
    return self.proficiency_bonus() if self.insight_proficient() else 0
  
  def perception_proficiency(self):
    return self.proficiency_bonus() if self.perception_proficient() else 0
  
  def to_dict(self):
    _serialized_casted_effects = []
    _serialized_effects = {}
    for casted_effect in self.casted_effects:
      _copy = copy.copy(casted_effect)
      if 'target' in casted_effect:
        _copy['target'] = casted_effect['target'].entity_uid
      _serialized_casted_effects.append(_copy)

    for k, descriptors in self.effects.items():
      _descriptor_arr = []
      for descriptor in descriptors:
        _descriptor = copy.copy(descriptor)
        if 'source' in _descriptor:
          _descriptor['source'] = _descriptor['source'].entity_uid
        _descriptor_arr.append(_descriptor)
      _serialized_effects[k] = _descriptor_arr


    base_dict = {
      'session': self.session,
      'name': self.name,
      'classes': self.c_class(),
      'hp': self.attributes['hp'],
      'type': 'pc',
      'properties': self.properties,
      'inventory': self.inventory,
      'entity_uid': self.entity_uid,
      'group': self.group,
      'effects': _serialized_effects,
      'casted_effects': _serialized_casted_effects,
      'statuses': self.statuses,
      'perception_results': self.perception_results,
      # 'entity_event_hooks': self.entity_event_hooks,
      'concentration': self.concentration,
      'death_fails': self.death_fails,
      'death_saves': self.death_saves,
      'hidden_stealth': self.hidden_stealth,
      '_temp_hp': self._temp_hp
    }
    return base_dict

  def from_dict(data):
    properties = data['properties']
    player_character = PlayerCharacter(data['session'], properties=properties, name=data['name'])
    player_character.entity_uid = data['entity_uid']
    player_character.attributes['hp'] = data['hp']
    player_character.inventory = data['inventory']
    player_character.effects = data['effects']
    player_character.casted_effects = data['casted_effects']
    player_character.statuses = data['statuses']
    player_character.perception_results = data['perception_results']
    player_character.group = properties.get('group', 'a')
    # player_character.entity_event_hooks = data['entity_event_hooks']
    player_character.death_fails = data.get('death_fails', 0)
    player_character.death_saves = data.get('death_saves', 0)
    player_character.concentration = data['concentration']
    player_character.hidden_stealth = data['hidden_stealth']
    player_character._temp_hp = data['_temp_hp']
    return player_character