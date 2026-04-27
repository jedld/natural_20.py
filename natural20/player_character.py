from natural20.entity import Entity
from natural20.die_roll import DieRoll
from natural20.entity_class.fighter import Fighter
from natural20.entity_class.rogue import Rogue
from natural20.entity_class.wizard import Wizard
from natural20.entity_class.cleric import Cleric
from natural20.entity_class.paladin import Paladin
from natural20.entity_class.warlock import Warlock
from natural20.entity_class.ranger import Ranger
from natural20.entity_class.monk import Monk
from natural20.entity_class.bard import Bard
from natural20.entity_class.druid import Druid
from natural20.entity_class.barbarian import Barbarian
from natural20.actions.action_surge_action import ActionSurgeAction
from natural20.actions.rage_action import RageAction, RecklessAttackAction, EndRageAction
from natural20.actions.flurry_of_blows_action import FlurryOfBlowsAction
from natural20.actions.patient_defense_action import PatientDefenseAction
from natural20.actions.step_of_the_wind_action import StepOfTheWindAction
from natural20.actions.martial_arts_bonus_attack_action import MartialArtsBonusAttackAction
from natural20.actions.feline_agility_action import FelineAgilityAction
from natural20.actions.bardic_inspiration_action import BardicInspirationAction
from natural20.actions.wild_shape_action import WildShapeAction, RevertWildShapeAction, WildShapeAttackAction
from natural20.entity_class import wild_shape as _wild_shape
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction
from natural20.actions.look_action import LookAction
from natural20.actions.move_action import MoveAction
from natural20.actions.dodge_action import DodgeAction
from natural20.actions.ready_action import ReadyAction
from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.hide_action import HideAction, HideBonusAction
from natural20.actions.disengage_action import DisengageAction, DisengageBonusAction
from natural20.actions.dash import DashAction, DashBonusAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.lay_on_hands_action import LayOnHandsAction
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
from natural20.actions.find_familiar_action import FindFamiliarAction
from natural20.actions.summon_familiar_action import SummonFamiliarAction
from natural20.actions.mage_hand_action import MageHandAction
from natural20.actions.speak_action import SpeakAction
from natural20.utils.action_builder import autobuild
from natural20.concern.container import Container
from natural20.utils.movement import compute_actual_moves
from natural20.concern.lootable import Lootable
from natural20.concern.inventory import Inventory
import yaml
import os
import copy
import uuid
from datetime import datetime, timezone
import pdb


class PlayerCharacter(Entity, Fighter, Rogue, Wizard, Cleric, Paladin, Warlock, Ranger, Monk, Bard, Druid, Barbarian, Lootable, Inventory):
  ACTION_LIST = [
    SpellAction,
    AttackAction,
    MartialArtsBonusAttackAction,
    FlurryOfBlowsAction,
    PatientDefenseAction,
    StepOfTheWindAction,
    FelineAgilityAction,
    BardicInspirationAction,
    WildShapeAction,
    RevertWildShapeAction,
    RageAction,
    EndRageAction,
    RecklessAttackAction,
    HideAction,
    HideBonusAction,
    DashAction,
    DashBonusAction,
    DisengageAction,
    DisengageBonusAction,
    DodgeAction,
    ReadyAction,
    MoveAction,
    ProneAction,
    SecondWindAction,
    LayOnHandsAction,
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
    LookAction,
    FindFamiliarAction,
    SummonFamiliarAction,
    MageHandAction,
    SpeakAction
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

    # Player characters have dialog capability by default
    self.dialog = True

    # use ordered dict to maintain order of spell slots
    self.spell_slots = {}
    with open(f"{self.session.root_path}/races/{race_file}.yml") as file:
      self.race_properties = yaml.safe_load(file)

    # Merge subrace features with base race features
    if self.subrace() and self.race_properties.get('subrace', {}).get(self.subrace(), {}).get('race_features'):
      self.race_properties['race_features'] = self.race_properties.get('race_features', []) + self.race_properties['subrace'][self.subrace()]['race_features']

    self.ability_scores = self.properties.get('ability', {})
    self.load_inventory()
    self.class_properties = {}
    self._current_hit_die = {}
    self.max_hit_die = {}
    self.resistances = list(self.properties.get("resistances", []))
    # Merge race-level damage resistances (e.g. Tiefling Hellish Resistance).
    for r in self.race_properties.get('resistances', []) or []:
      if r not in self.resistances:
        self.resistances.append(r)
    if self.subrace():
      sub = self.race_properties.get('subrace', {}).get(self.subrace(), {}) or {}
      for r in sub.get('resistances', []) or []:
        if r not in self.resistances:
          self.resistances.append(r)
    self.entity_uid =  self.properties.get('entity_uid', str(uuid.uuid4()))

    # Per-character journal: a chronological list of dict entries.
    # Each entry: {id, ts, kind, title, text, source, map_name, tags}.
    # Auto-populated when the player encounters narration; PCs may also
    # add manual entries via the character sheet UI or the local /talk
    # chat slash commands ("/journal add ..."). Survives save/load.
    self.journal = []

    for klass, level in self.properties.get('classes', {}).items():
      setattr(self, f"{klass}_level", level)
      getattr(self, f"initialize_{klass}")()
      with open(f"{self.session.root_path}/char_classes/{klass}.yml") as file:
        character_class_properties = yaml.safe_load(file)
      self.max_hit_die[klass] = level

      hit_die_details = DieRoll.parse(character_class_properties['hit_die'])
      self._current_hit_die[int(hit_die_details.die_type)] = level
      self.class_properties[klass] = character_class_properties

    self.attributes["hp"] = self.properties.get('hp', copy.deepcopy(self.max_hp()))

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
      return self.properties.get('subrace')
  
  def speed(self):
    if _wild_shape.is_wild_shaped(self):
      beast = self._wild_shape_state.get('beast_props', {})
      beast_speed = beast.get('speed')
      if beast_speed is not None:
        return beast_speed
    effective_speed = self.race_properties.get('subrace', {}).get(self.subrace(), {}).get('base_speed') or self.race_properties.get('base_speed')

    # Monk - Unarmored Movement (5e SRD): bonus speed while wearing no
    # armor and not wielding a shield.
    if self.class_feature('unarmored_movement') and getattr(self, 'monk_level', None):
      if not self._wearing_armor_or_shield():
        from natural20.entity_class.monk import UNARMORED_MOVEMENT_BONUS
        idx = max(1, min(self.monk_level, len(UNARMORED_MOVEMENT_BONUS))) - 1
        effective_speed = (effective_speed or 0) + UNARMORED_MOVEMENT_BONUS[idx]

    if self.has_effect('speed_override'):
      effective_speed = self.eval_effect('speed_override', { "stacked": True, "value" : effective_speed})

    return effective_speed

  def climb_speed(self):
    return self.race_properties.get('climb_speed')

  def reset_turn(self, battle):
    entity_state = battle.entity_state_for(self)
    # Tabaxi Feline Agility recharges when the creature moves 0 ft on a turn.
    if entity_state is not None and self.class_feature('feline_agility'):
      last_start = getattr(self, '_feline_movement_start', None)
      remaining = entity_state.get('movement', 0)
      # If no movement was consumed last turn, recharge Feline Agility.
      if last_start is not None and last_start > 0 and remaining >= last_start:
        self.feline_agility_used = False
    super().reset_turn(battle)
    if entity_state is not None:
      self._feline_movement_start = entity_state.get('movement', 0)

  def _wearing_armor_or_shield(self):
    if not self.equipped:
      return False
    try:
      with open(os.path.join(self.session.root_path, 'items', 'equipment.yml')) as file:
        equipments = yaml.safe_load(file)
    except FileNotFoundError:
      return False
    for item_id in self.equipped:
      meta = equipments.get(item_id)
      if not meta:
        continue
      if meta.get('type') in ('armor', 'shield'):
        return True
    return False

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

  def conversable(self):
    return True

  def armor_class(self):
    if _wild_shape.is_wild_shaped(self):
      beast = self._wild_shape_state.get('beast_props', {})
      ac = beast.get('default_ac')
      if ac is not None:
        return ac
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
    if map is None and battle is not None:
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
          if _wild_shape.is_wild_shaped(self):
            action_list = action_list + self._wild_shape_attack_actions(session, battle, auto_target=auto_target)
          else:
            action_list = action_list + self._player_character_attack_actions(session, battle, auto_target=auto_target)
        elif action_type == TwoWeaponAttackAction:
          if _wild_shape.is_wild_shaped(self):
            continue
          action_list = action_list + self._player_character_attack_actions(session, battle, second_weapon=True, auto_target=auto_target)
        elif action_type == DodgeAction:
          action_list.append(DodgeAction(session, self, 'dodge'))
        elif action_type == ReadyAction:
          action_list.append(ReadyAction(session, self, 'ready'))
        elif action_type == DisengageAction:
          action_list.append(DisengageAction(session, self, 'disengage'))
        elif action_type == SecondWindAction:
          action_list.append(SecondWindAction(session, self, 'second_wind'))
        elif action_type == LayOnHandsAction:
          action_list.append(LayOnHandsAction(session, self, 'lay_on_hands'))
        elif action_type == FirstAidAction:
          action_list.append(FirstAidAction(session, self, 'first_aid'))
        elif action_type == ActionSurgeAction:
          action_list.append(ActionSurgeAction(session, self, 'action_surge'))
        elif action_type == MartialArtsBonusAttackAction:
          base_action = MartialArtsBonusAttackAction(session, self, 'attack')
          if not auto_target:
            action_list.append(base_action)
          else:
            for target in battle.valid_targets_for(self, base_action, target_types=['enemies']):
              targeted = base_action.clone()
              targeted.target = target
              action_list.append(targeted)
        elif action_type == FlurryOfBlowsAction:
          base_action = FlurryOfBlowsAction(session, self, 'flurry_of_blows')
          if not auto_target:
            action_list.append(base_action)
          else:
            for target in battle.valid_targets_for(self, base_action, target_types=['enemies']):
              targeted = FlurryOfBlowsAction(session, self, 'flurry_of_blows')
              targeted.target = target
              targeted.second_target = target
              action_list.append(targeted)
        elif action_type == PatientDefenseAction:
          action_list.append(PatientDefenseAction(session, self, 'patient_defense'))
        elif action_type == BardicInspirationAction:
          if auto_target:
            action_list = action_list + autobuild(self.session, BardicInspirationAction, self, battle)
          else:
            action_list.append(BardicInspirationAction(session, self, 'bardic_inspiration'))
        elif action_type == WildShapeAction:
          action_list.append(WildShapeAction(session, self, 'wild_shape'))
        elif action_type == RevertWildShapeAction:
          action_list.append(RevertWildShapeAction(session, self, 'revert_wild_shape'))
        elif action_type == RageAction:
          action = RageAction(session, self, 'rage')
          action.as_bonus_action = True
          action_list.append(action)
        elif action_type == EndRageAction:
          action = EndRageAction(session, self, 'end_rage')
          action.as_bonus_action = True
          action_list.append(action)
        elif action_type == RecklessAttackAction:
          action_list.append(RecklessAttackAction(session, self, 'reckless_attack'))
        elif action_type == StepOfTheWindAction:
          action_list.append(StepOfTheWindAction(session, self, 'step_of_the_wind', { 'mode': 'disengage' }))
          action_list.append(StepOfTheWindAction(session, self, 'step_of_the_wind', { 'mode': 'dash' }))
        elif action_type == FelineAgilityAction:
          action_list.append(FelineAgilityAction(session, self, 'feline_agility'))
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
        elif action_type == FindFamiliarAction:
          action_list.append(FindFamiliarAction(session, self, 'dismiss_familiar'))
        elif action_type == SummonFamiliarAction:
          action_list.append(SummonFamiliarAction(session, self, 'summon_familiar'))
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
              # Prevent corner cutting on diagonals: both adjacent orthogonals must be free
              if abs(x_pos) == 1 and abs(y_pos) == 1:
                adj1_ok = map.bidirectionally_passable(self, cur_x + x_pos, cur_y, (cur_x, cur_y), battle, allow_squeeze=False) and \
                          map.placeable(self, cur_x + x_pos, cur_y, battle, squeeze=False)
                adj2_ok = map.bidirectionally_passable(self, cur_x, cur_y + y_pos, (cur_x, cur_y), battle, allow_squeeze=False) and \
                          map.placeable(self, cur_x, cur_y + y_pos, battle, squeeze=False)
                if not (adj1_ok and adj2_ok):
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
        elif action_type == DropGrappleAction:
          action = DropGrappleAction(session, self, 'drop_grapple')
          action_list.append(action)
        elif action_type == EscapeGrappleAction:
          action = EscapeGrappleAction(session, self, 'escape_grapple')
          action_list.append(action)
        elif action_type == SpellAction:
          if _wild_shape.is_wild_shaped(self):
            continue
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
              for interaction, details in objects.available_interactions(self, battle, admin=self.is_admin).items():
                action = InteractAction(session, self, 'interact', { "target": objects,
                                                                              "object_action": [interaction, details] })
                if details.get('disabled'):
                  action.disabled = True
                  action.disabled_reason = self.t(details['disabled_text'])

                action_list.append(action)
        elif action_type == FindFamiliarAction:
          action_list.append(FindFamiliarAction(session, self, 'dismiss_familiar'))
        elif action_type == MageHandAction:
          action_list.append(MageHandAction(session, self, 'mage_hand_command'))
        elif action_type == SpeakAction:
          action_list.append(SpeakAction(session, self, 'speak'))
    # Phase 4: also consult the class-feature registry. Existing branches
    # above keep working; this is an additive opt-in extension point.
    try:
      from natural20.utils.class_feature_registry import collect_class_feature_actions
      action_list.extend(collect_class_feature_actions(session, self, battle))
    except Exception:
      pass
    return action_list



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

  def unarmed_strike_info(self):
    """Return a summary of this character's unarmed strike for the UI.

    Includes attack bonus, damage formula, damage type, range, and the
    governing ability. Honors the Monk class' Martial Arts feature
    (DEX in place of STR; martial arts die in place of base damage).
    """
    from natural20.weapons import damage_modifier
    weapon = self.session.load_weapon('unarmed_attack')
    if not weapon:
      return None
    attack_mod = self.attack_ability_mod(weapon)
    if self.proficient_with_weapon(weapon):
      attack_mod += self.proficiency_bonus()
    damage_roll = damage_modifier(self, weapon)

    ability = 'STR'
    if (
      getattr(self, 'class_feature', None) and self.class_feature('martial_arts')
      and getattr(self, 'is_monk_weapon', None) and self.is_monk_weapon(weapon)
      and self.dex_mod() > self.str_mod()
    ):
      ability = 'DEX'

    properties = []
    if getattr(self, 'class_feature', None) and self.class_feature('martial_arts'):
      properties.append('Martial Arts')
    if getattr(self, 'class_feature', None) and self.class_feature('cats_claws'):
      properties.append("Cat's Claws")
    damage_type = weapon.get('damage_type', 'bludgeoning')
    if getattr(self, 'class_feature', None) and self.class_feature('cats_claws'):
      damage_type = 'slashing'
    name = weapon.get('name', 'Unarmed Strike')
    if getattr(self, 'class_feature', None) and self.class_feature('cats_claws'):
      name = "Cat's Claws"
    return {
      'name': name,
      'attack_bonus': attack_mod,
      'damage': damage_roll,
      'damage_type': damage_type,
      'range': weapon.get('range', 5),
      'ability': ability,
      'properties': properties,
    }

  def _wild_shape_attack_actions(self, session, battle, opportunity_attack=False, auto_target=True):
    """Build attack actions sourced from the active beast statblock."""
    actions = []
    for npc_action in (getattr(self, 'npc_actions', None) or []):
      if not AttackAction.can(self, battle, {
        'npc_action': npc_action,
        'opportunity_attack': opportunity_attack,
      }):
        continue
      attack = WildShapeAttackAction(session, self, 'attack')
      attack.npc_action = npc_action
      actions.append(attack)
    if battle and auto_target:
      final = []
      for action in actions:
        for target in battle.valid_targets_for(self, action, target_types=['enemies']):
          targeted = action.clone()
          targeted.target = target
          final.append(targeted)
      return final
    return actions

  def is_wild_shaped(self):
    return _wild_shape.is_wild_shaped(self)

  def wild_shape_form(self):
    return _wild_shape.current_form(self)

  def after_death(self):
      pass

  def token_image_transform(self):
      if self.dead():
          return "transform: rotate(180deg) scale(0.5); filter: brightness(50%) sepia(100%) hue-rotate(180deg); opacity: 0.5; "
      return None

  def placeable(self):
    if not self.dead():
      return False
    return True
  
  def use(self, entity, result, session=None):
    if result['action'] == 'give':
      self.transfer(result['battle'], result['target'], result['source'], result['items'])
    elif result['action'] == 'loot':
      self.transfer(result.get('battle'), result.get('source'), result.get('target'), result.get('items'))
      return True
    else:
      raise NotImplementedError(f"unknown action {result['action']}")

  def prepared_spells(self):
    return self.properties.get('cantrips', []) + self.properties.get('prepared_spells', [])

  # Consumes a character's spell slot
  def consume_spell_slot(self, level, character_class=None, qty=1):
    if character_class is None:
      character_class = list(self.spell_slots.keys())[0]

    if level <= 0:
      return

    slots = self.spell_slots.get(character_class, {})
    if not slots:
      return

    target_level = level if slots.get(level, 0) >= qty else self.next_spell_slot_level(character_class, level)
    if target_level is None:
      return

    self.spell_slots[character_class][target_level] = max(self.spell_slots[character_class][target_level] - qty, 0)

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

    # Monk - Unarmored Defense (5e SRD): while wearing no armor and no
    # shield, AC = 10 + DEX modifier + WIS modifier.
    if armor is None and shield is None and self.class_feature('unarmored_defense_monk'):
      return 10 + self.dex_mod() + self.wis_mod()

    # Barbarian - Unarmored Defense (5e SRD): while wearing no armor,
    # AC = 10 + DEX modifier + CON modifier.  A shield is allowed and
    # adds its AC bonus on top.
    if armor is None and self.class_feature('unarmored_defense_barbarian'):
      return 10 + self.dex_mod() + self.con_mod() + (0 if shield is None else shield['bonus_ac'])

    armor_ac = 10 + self.dex_mod() if armor is None else armor['ac'] + min(self.dex_mod(), armor['mod_cap'] if 'mod_cap' in armor else self.dex_mod()) + (1 if self.class_feature('defense') else 0)

    return armor_ac + (0 if shield is None else shield['bonus_ac'])

  def any_class_feature(self, features):
    return any(self.class_feature(f) for f in features)
  
  def darkvision(self, distance):
    if super().darkvision(distance):
      return True

    return bool(self.race_properties.get('darkvision', None) and (self.race_properties['darkvision'] >= distance))

  def next_spell_slot_level(self, character_class, minimum_level):
    if minimum_level <= 0:
      return 0

    slots = self.spell_slots.get(character_class, {})
    if not slots:
      return None

    max_slot_level = max(slots.keys()) if slots else 0
    for slot_level in range(max(1, minimum_level), max_slot_level + 1):
      if slots.get(slot_level, 0) > 0:
        return slot_level

    return None

  def spell_slots_count(self, level=None, character_class=None):
    if character_class not in self.spell_slots:
      if character_class is None:
        character_class = list(self.spell_slots.keys())
      else:
        return 0

    if isinstance(character_class, str):
      slots = self.spell_slots[character_class]
      return slots.get(level, 0) if level else sum(slots.values())

    total = 0
    for klass in character_class:
      slots = self.spell_slots[klass]
      total += slots.get(level, 0) if level else sum(slots.values())
    return total


  # Returns the number of spell slots
  # @param level [Integer]
  # @return [Integer]
  def max_spell_slots(self, level, character_class=None):
    if character_class is None:
      character_class = list(self.spell_slots.keys())[0]

    if hasattr(self, f"max_slots_for_{character_class}"):
      return getattr(self, f"max_slots_for_{character_class}")(level)

    return 0
  
  def available_spells(self, battle, touch=False):
    spell_list = self.spell_list(battle, touch)
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

    return sorted(set(super().languages() + class_languages + racial_languages))
  
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

  def take_damage(self, dmg, battle=None, damage_type='piercing', session=None,
                  item=None, critical=False, roll_info=None, sneak_attack=None):
    if not _wild_shape.is_wild_shaped(self):
      return super().take_damage(dmg, battle=battle, damage_type=damage_type,
                                  session=session, item=item, critical=critical,
                                  roll_info=roll_info, sneak_attack=sneak_attack)

    # Wild-shaped: damage hits the beast pool first; on 0 HP the druid
    # reverts and any overflow damage rolls onto the saved druid HP.
    pre_hp = self.attributes.get('hp', 0)
    # Estimate post-resistance damage so overflow is computed before the
    # engine clamps the beast pool to zero.
    effective_dmg = dmg
    if self.immune_to(damage_type):
      effective_dmg = 0
    elif self.resistant_to(damage_type):
      effective_dmg = dmg // 2
    elif self.vulnerable_to(damage_type):
      effective_dmg = dmg * 2
    result = super().take_damage(dmg, battle=battle, damage_type=damage_type,
                                  session=session, item=item, critical=critical,
                                  roll_info=roll_info, sneak_attack=sneak_attack)
    if self.attributes.get('hp', 0) <= 0:
      overflow = max(0, effective_dmg - pre_hp)
      # If the engine already flagged us unconscious during the beast
      # take_damage, clear it before reverting so the druid form can be
      # evaluated cleanly against its restored HP.
      if 'unconscious' in self.statuses:
        self.statuses.remove('unconscious')
      _wild_shape.revert(self, overflow_damage=overflow, battle=battle)
      if session is None:
        session = battle.session if battle else getattr(self, 'session', None)
      if session:
        session.event_manager.received_event({
          'source': self,
          'event': 'wild_shape_revert',
          'reason': 'beast_dropped',
        })
    return result

  # ── Journal ────────────────────────────────────────────────────────────
  def add_journal_entry(self, text, kind='note', title=None, source=None,
                        map_name=None, tags=None, timestamp=None):
    """Append an entry to this character's journal.

    Returns the stored entry dict. ``kind`` is a free-form category such as
    ``'note'`` (player-authored), ``'narration'`` (auto-captured), or
    ``'dm'`` (added on behalf of the DM). Duplicate consecutive narration
    entries with identical ``(kind, text, source)`` are de-duplicated to
    keep the log readable when a narration fires for several PCs at once.
    """
    if not isinstance(text, str):
      text = str(text or '')
    text = text.strip()
    if not text:
      return None
    if not isinstance(self.journal, list):
      self.journal = []
    if kind == 'narration' and self.journal:
      last = self.journal[-1]
      if (last.get('kind') == 'narration'
          and last.get('text') == text
          and last.get('source') == source):
        return last
    entry = {
      'id': str(uuid.uuid4()),
      'ts': timestamp or datetime.now(timezone.utc).isoformat(),
      'kind': kind,
      'title': title,
      'text': text,
      'source': source,
      'map_name': map_name,
      'tags': list(tags) if tags else [],
    }
    self.journal.append(entry)
    return entry

  def search_journal(self, query=None, kind=None, limit=None):
    """Return journal entries matching ``query`` (case-insensitive
    substring across title/text/tags). When ``query`` is empty the full
    list is returned in chronological order. ``limit`` truncates the
    most-recent N entries when supplied.
    """
    entries = list(self.journal or [])
    if kind:
      entries = [e for e in entries if e.get('kind') == kind]
    if query:
      needle = query.strip().lower()
      if needle:
        def _matches(entry):
          for field in ('title', 'text'):
            value = entry.get(field) or ''
            if needle in value.lower():
              return True
          for tag in entry.get('tags') or []:
            if needle in str(tag).lower():
              return True
          return False
        entries = [e for e in entries if _matches(e)]
    if limit is not None and limit > 0:
      entries = entries[-int(limit):]
    return entries

  def remove_journal_entry(self, entry_id):
    """Delete the entry with the matching id. Returns ``True`` on success."""
    if not entry_id or not isinstance(self.journal, list):
      return False
    before = len(self.journal)
    self.journal = [e for e in self.journal if e.get('id') != entry_id]
    return len(self.journal) != before

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


    # Per-class mutable resources that should round-trip
    class_resources = {}
    for attr in (
      'arcane_recovery',
      'second_wind_count',
      'lay_on_hands_count',
      'lay_on_hands_max_pool',
      'divine_sense_count',
      'divine_sense_max_count',
      'ki_count',
      'max_ki',
      'bardic_inspiration_count',
      'bardic_inspiration_max',
      'wild_shape_count',
      'wild_shape_max',
      'rage_count',
      'rage_max',
      'raging',
      'rage_rounds_remaining',
      'reckless_attack_active',
      'relentless_endurance_used',
      'feline_agility_used',
    ):
      if hasattr(self, attr):
        class_resources[attr] = getattr(self, attr)

    # If wild-shaped, scrub the overlay from the persisted properties so
    # the humanoid form is what gets re-instantiated by from_dict.
    persisted_properties = _wild_shape.scrub_properties_for_serialization(
      self.properties, getattr(self, '_wild_shape_state', None))

    base_dict = {
      'session': self.session,
      'name': self.name,
      'classes': self.c_class(),
      'hp': self.attributes['hp'],
      'type': 'pc',
      'properties': persisted_properties,
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
      '_temp_hp': self._temp_hp,
      'spell_slots': {k: dict(v) for k, v in self.spell_slots.items()},
      '_current_hit_die': dict(self._current_hit_die),
      'class_resources': class_resources,
      'resources': {name: pool.to_dict() for name, pool in (getattr(self, 'resources', None) or {}).items()},
      '_wild_shape_state': copy.deepcopy(getattr(self, '_wild_shape_state', None)),
      'npc_actions': copy.deepcopy(getattr(self, 'npc_actions', None) or []),
      'journal': copy.deepcopy(getattr(self, 'journal', []) or []),
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
    if 'spell_slots' in data:
      player_character.spell_slots = {k: dict(v) for k, v in data['spell_slots'].items()}
    if '_current_hit_die' in data:
      player_character._current_hit_die = dict(data['_current_hit_die'])
    for attr, value in (data.get('class_resources') or {}).items():
      setattr(player_character, attr, value)
    # Phase 4: rehydrate ResourcePool entries.
    if data.get('resources'):
      from natural20.resource_pool import ResourcePool
      player_character.resources = {
        name: ResourcePool.from_dict(pdata)
        for name, pdata in data['resources'].items()
      }
    if data.get('_wild_shape_state') is not None:
      player_character._wild_shape_state = data['_wild_shape_state']
      _wild_shape.reapply_after_load(player_character)
      # Re-set HP from persisted value (overlay set it to beast max).
      player_character.attributes['hp'] = data['hp']
    if data.get('npc_actions'):
      player_character.npc_actions = data['npc_actions']
    if data.get('journal'):
      player_character.journal = list(data['journal'])
    return player_character