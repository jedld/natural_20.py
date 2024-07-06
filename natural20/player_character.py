from natural20.entity import Entity
from natural20.die_roll import DieRoll
from natural20.entity_class.fighter import Fighter
from natural20.entity_class.rogue import Rogue
from natural20.entity_class.wizard import Wizard
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction
from natural20.actions.look_action import LookAction
from natural20.actions.move_action import MoveAction
from natural20.actions.dodge_action import DodgeAction
from natural20.actions.disengage_action import DisengageAction
from natural20.actions.dash import DashAction, DashBonusAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.stand_action import StandAction
from natural20.actions.prone_action import ProneAction
from natural20.utils.movement import compute_actual_moves
import yaml
import os
import copy

class PlayerCharacter(Entity, Fighter, Rogue, Wizard):
  ACTION_LIST = [
    LookAction, AttackAction, MoveAction, DisengageAction, DodgeAction, DashAction, DashBonusAction,
    TwoWeaponAttackAction, SecondWindAction, ProneAction
  ]

  def __init__(self, session, properties, name=None):
    super(PlayerCharacter, self).__init__(name, f"PC {name}", {})
    self.properties = properties
    
    if name is None:
      self.name = self.properties['name']
      
    race_file = self.properties['race']
    self.session = session
    self.equipped = self.properties.get('equipped', [])
    self.inventory = {}
    self.spell_slots = {}
    with open(f"{self.session.root_path}/races/{race_file}.yml") as file:
      self.race_properties = yaml.safe_load(file)


    self.ability_scores = self.properties.get('ability', {})

    for inventory in self.properties.get('inventory', []):
      inventory_type = inventory.get('type')
      inventory_qty = inventory.get('qty')
      if inventory_type:
        if inventory_type not in self.inventory:
          self.inventory[inventory_type] = {'type': inventory_type, 'qty': 0}
        self.inventory[inventory_type]['qty'] += inventory_qty

    self.class_properties = {}
    self.current_hit_die = {}
    self.max_hit_die = {}
    self.resistances = []

    for klass, level in self.properties.get('classes', {}).items():
      setattr(self, f"{klass}_level", level)
      getattr(self, f"initialize_{klass}")()
      with open(f"{self.session.root_path}/char_classes/{klass}.yml") as file:
        character_class_properties = yaml.safe_load(file)
      self.max_hit_die[klass] = level

      hit_die_details = DieRoll.parse(character_class_properties['hit_die'])
      self.current_hit_die[int(hit_die_details.die_type)] = level
      self.class_properties[klass] = character_class_properties

    self.attributes["hp"] = copy.deepcopy(self.max_hp())

  @staticmethod
  def load(session, path, override={}):
    with open(os.path.join(session.root_path, path), 'r') as file:
      properties = yaml.safe_load(file)
    properties.update(override)
    return PlayerCharacter(session, properties)

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
      effective_speed = self.eval_effect('speed_override', stacked=True, value=self.properties.get('speed'))

    return effective_speed
  
  def max_hp(self):
    if self.class_feature('dwarven_toughness'):
      return self.properties['max_hp'] + self.level
    else:
      return self.properties['max_hp']
    
  def melee_distance(self):
    if not self.properties['equipped']:
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

  def available_actions(self, session, battle, opportunity_attack=False):
    if self.unconscious():
      return []

    if opportunity_attack:
      if AttackAction.can(self, battle, { 'opportunity_attack': True }):
        return self._player_character_attack_actions(session, battle, opportunity_attack=True)
      else:
        return []

    action_list = []

    for action_type in self.ACTION_LIST:
      if action_type.can(self, battle):
        if action_type == LookAction:
          action_list.append(LookAction(session, self, 'look'))
        elif action_type == AttackAction:
          action_list = action_list + self._player_character_attack_actions(session, battle)
        elif action_type == TwoWeaponAttackAction:
          action_list = action_list + self._player_character_attack_actions(session, battle, second_weapon=True)
        elif action_type == DodgeAction:
          action_list.append(DodgeAction(session, self, 'dodge'))
        elif action_type == DisengageAction:
          action_list.append(DisengageAction(session, self, 'disengage'))
        elif action_type == SecondWindAction:
          action_list.append(SecondWindAction(session, self, 'second_wind'))
        elif action_type == DashBonusAction:
          action = DashBonusAction(session, self, 'dash_bonus')
          action.as_bonus_action = True
          action_list.append(action)
        elif action_type == DashAction:
          action = DashAction(session, self, 'dash')
          action_list.append(action)
        elif action_type == MoveAction:
          # generate possible moves
          cur_x, cur_y = battle.map.position_of(self)
          for x_pos in range(-1, 2):
            for y_pos in range(-1, 2):
              if x_pos == 0 and y_pos == 0:
                continue
              if battle.map.passable(self, cur_x + x_pos, cur_y + y_pos, battle, allow_squeeze=False) and battle.map.placeable(self, cur_x + x_pos, cur_y + y_pos, battle, squeeze=False):
                chosen_path = [[cur_x, cur_y], [cur_x + x_pos, cur_y + y_pos]]
                shortest_path = compute_actual_moves(self, chosen_path, battle.map, battle, self.available_movement(battle) // 5).movement
                if len(shortest_path) > 1:
                  # print(f"shortest_path: {shortest_path}")
                  move_action = MoveAction(session, self, 'move')
                  move_action.move_path = shortest_path
                  action_list.append(move_action)
        elif action_type == ProneAction:
          action = ProneAction(session, self, 'prone')
          action_list.append(action)
        elif action_type == StandAction:
          action = StandAction(session, self, 'stand')
          action_list.append(action)

    return action_list

  def _player_character_attack_actions(self, session, battle, opportunity_attack=False, second_weapon=False):
    # check all equipped and create attack for each
    valid_weapon_types = ['melee_attack'] if opportunity_attack else ['ranged_attack', 'melee_attack']

    weapon_attacks = []
    for item in self.properties['equipped']:
      weapon_detail = session.load_weapon(item)
      if weapon_detail is None:
        continue
      if weapon_detail['type'] not in valid_weapon_types:
        continue
      if 'ammo' in weapon_detail and not self.item_count(weapon_detail['ammo']) > 0:
        continue

      attacks = []

      attack_class = AttackAction
      attack_type = 'attack'
      if second_weapon:
        attack_class = TwoWeaponAttackAction
        attack_type = 'two_weapon_attack'

      action = attack_class(session, self, attack_type)
      action.using = item
      attacks.append(action)
      if not opportunity_attack and weapon_detail.get('properties') and 'thrown' in weapon_detail.get('properties', []):
        action = attack_class(session, self, attack_type)
        action.using = item
        action.thrown = True
        attacks.append(action)

      weapon_attacks.extend(attacks)

    unarmed_attack = attack_class(session, self, attack_type)
    unarmed_attack.using = 'unarmed_attack'

    pre_target_attack_list = weapon_attacks + [unarmed_attack]

    # assign possible attack targets
    final_attack_list = []
    for action in pre_target_attack_list:
      valid_targets = battle.valid_targets_for(self, action)
      for target in valid_targets:
        targeted_action = copy.copy(action)
        targeted_action.target = target
        final_attack_list.append(targeted_action)
    return final_attack_list


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
    if self.race_properties.get('skills') and prof in self.race_properties['skills']:
      return True
    if prof in self.weapon_proficiencies():
      return True

    return super().proficient(prof)


  def equipped_ac(self):
    with open(os.path.join(self.session.root_path, 'items', 'equipment.yml')) as file:
      equipments = yaml.load(file, Loader=yaml.FullLoader)
    equipped_meta = [equipments[e] for e in self.equipped if e in equipments]
    armor = next((equipment for equipment in equipped_meta if equipment['type'] == 'armor'), None)
    shield = next((equipment for equipment in equipped_meta if equipment['type'] == 'shield'), None)

    armor_ac = 10 + self.dex_mod() if armor is None else armor['ac'] + min(self.dex_mod(), armor['mod_cap'] if 'mod_cap' in armor else self.dex_mod()) + (1 if self.class_feature('defense') else 0)

    return armor_ac + (0 if shield is None else shield['bonus_ac'])


