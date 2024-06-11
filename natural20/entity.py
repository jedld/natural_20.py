from natural20.die_roll import DieRoll
import math
import pdb
from natural20.event_manager import EventManager
class Entity():
    def __init__(self, name, description, attributes = {}, event_manager = EventManager()):
        self.name = name
        self.description = description
        self.attributes = attributes
        self.statuses = []
        self.ability_scores = {}
        self.entity_event_hooks = {}
        self.effects = {}
        self.flying = False
        self.casted_effects = []
        self.death_fails = 0
        self.death_saves = 0
        self.event_handlers = {}
        self.event_manager = event_manager
    
    def __str__(self):
        return f"{self.name}"
    
    def __repr__(self):
        return f"{self.name}"
    
    def name(self):
        return self.name
    
    def hp(self):
        return self.attributes["hp"]
    
   
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
        
    def long_jump_distance(self):
        return self.ability_scores.get('str')

    def perception_check(self, battle):
        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return 0

        return DieRoll.roll(f"1d20+{self.wis_mod()}", description="perception check", entity=self, battle=battle)

    def drop_grapple(self):
        if hasattr(self, 'grappling'):
            for target in self.grappling:
                self.ungrapple(target)

    def dead(self):
        return 'dead' in self.statuses
    
    def make_dead(self):
        if not self.dead():
            self.event_manager.received_event({ 'source': self, 'event': 'died' })
            # print(f"{self.name} died. :(")
            self.drop_grapple()
            self.statuses.append('dead')
            if 'stable' in self.statuses:
                self.statuses.remove('stable')
            if 'unconscious' in self.statuses:
                self.statuses.remove('unconscious')

    def make_unconscious(self):
        if not self.unconscious() and not self.dead():
            self.drop_grapple()
            self.event_manager.received_event({ 'source': self, 'event': 'unconscious' })
            # print(f"{self.name} is unconscious.")

            self.statuses.append('prone')
            self.statuses.append('unconscious')
            
    def grappled(self):
        return 'grappled' in self.statuses
    
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

    def hiding(self, battle):
        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return False

        return ':hiding' in entity_state.get('statuses', [])
    
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

    def is_grappling(self):
        if not hasattr(self, 'grappling'):
            self.grappling = []
        return len(self.grappling) > 0
    
    def grappling_targets(self):
        if not hasattr(self, 'grappling'):
            self.grappling = []
        return self.grappling

    def is_flying(self):
        return bool(self.flying)
    
    def fly(self):
        if self.properties.get('speed_fly'):
            self.flying = True 
    
    def can_fly(self):
        return self.properties.get('speed_fly')
    
    def is_flying(self):
        return self.flying
    
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
                if distance <= self.melee_distance() + 0.5:
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

    def initiative(self, battle=None):
        roll = DieRoll.roll(f"1d20+{self.dex_mod()}", description="initiative", entity=self, battle=battle)
        value = float(roll.result()) + self.ability_scores.get('dex') / 100.0
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

    def modifier_table(self, value):
        mod_table = [[1, 1, -5],
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
                pdb.set_trace()
                raise ValueError(f"invalid value {value}")
            if low <= value <= high:
                return mod
        return None
    
    def reset_turn(self, battle):
        entity_state = battle.entity_state_for(self)
        entity_state.update({
            'action': 1,
            'bonus_action': 1,
            'reaction': 1,
            'movement': self.speed(),
            'free_object_interaction': 1,
            'active_perception': 0,
            'active_perception_disadvantage': 0,
            'two_weapon': None
        })

        if 'dodge' in entity_state['statuses']:
            entity_state['statuses'].remove('dodge')

        if 'disengage' in entity_state['statuses']:
            entity_state['statuses'].remove('disengage')

        battle.dismiss_help_actions_for(self)
        battle.event_manager.received_event({'source': self, 'event': 'start_of_turn'})
        self.resolve_trigger('start_of_turn')
        self._cleanup_effects()
        return entity_state
    
    def resolve_trigger(self, event_type, opts={}):
        if event_type in self.entity_event_hooks:
            active_hook = [effect for effect in self.entity_event_hooks[event_type] if not effect.get('expiration') or effect['expiration'] > self.session.game_time][-1]
            if active_hook:
                active_hook['handler'].send(active_hook['method'], self, {**opts, 'effect': active_hook['effect']})


    def _cleanup_effects(self):
        for key, value in self.effects.items():
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
        return battle.entity_state_for(self).get('action')

    def total_reactions(self, battle):
        return battle.entity_state_for(self).get('reaction')

    def free_object_interaction(self, battle):
        if battle is None:
            return True

        return (battle.entity_state_for(self).get('free_object_interaction', 0) > 0)

    def total_bonus_actions(self, battle):
        return battle.entity_state_for(self).get('bonus_action')

    def available_movement(self, battle):
        if battle is None:
            return self.speed

        if self.grappled() or self.unconscious():
            return 0

        return battle.entity_state_for(self).get('movement')

    def available_spells(self):
        return []
    
    def familiar(self):
      return self.properties.get('familiar')

    def speed(self):
        c_speed = self.properties['speed_fly'] if self.is_flying() else self.properties['speed']

        if self.has_effect('speed_override'):
            c_speed = self.eval_effect('speed_override', stacked=True, value=c_speed)

        return c_speed
    

    def stable(self):
        return 'stable' in self.statuses
    
    def prone(self):
        return 'prone' in self.statuses
   
    def squeezed(self):
        return 'squeezed' in self.statuses
    
    def do_dodge(self, battle):
        entity_state = battle.entity_state_for(self)
        entity_state['statuses'].add('dodge')

    def dodge(self, battle):
        if not battle:
            return False

        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return False

        return 'dodge' in entity_state.get('statuses', [])
    
    def break_stealth(self, battle):
        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return
        if 'hiding' in entity_state['statuses']:
            entity_state['statuses'].remove('hiding')
        entity_state['stealth'] = 0

    def trigger_event(self, event_name, battle, session, map, event):
        if event_name in self.event_handlers:
            callback = self.event_handlers[event_name]
            callback(battle, session, self, map, event)

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
    def melee_squares(self, map, target_position=None, adjacent_only=False, squeeze=False):
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

                        position = [sq[0] + adjusted_x_off, sq[1] + adjusted_y_off]

                        if (position in entity_squares) or (position in result) or (position[0] < 0) or (position[0] >= map.size[0]) or (position[1] < 0) or (position[1] >= map.size[1]):
                            continue

                        result.append(position)
        else:
            step = self.melee_distance / map.feet_per_grid
            cur_x, cur_y = target_position or map.entity_or_object_pos(self)
            for x_off in range(-step, step+1):
                for y_off in range(-step, step+1):
                    if x_off == 0 and y_off == 0:
                        continue

                    # adjust melee position based on token size
                    adjusted_x_off = x_off
                    adjusted_y_off = y_off

                    if x_off < 0:
                        adjusted_x_off -= self.token_size - 1
                    if y_off < 0:
                        adjusted_y_off -= self.token_size - 1

                    position = [cur_x + adjusted_x_off, cur_y + adjusted_y_off]

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

    def equipped_items(self):
        equipped_arr = self.properties.get('equipped', [])
        equipped_list = []
        for k in equipped_arr:
            item = self.session.load_thing(k)
            if not item:
                raise Exception(f"unknown item {k}")
            equipped_list.append(self._to_item(k, item))

        return equipped_list
    
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
    
    def proficient(self, prof):
        return (prof in self.properties.get('skills', []) or
                prof in self.properties.get('tools', []) or
                prof in self.properties.get('weapon_proficiencies', []) or
                f"{prof}_save" in self.properties.get('saving_throw_proficiencies', []))
    
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
            'label': item.get('label', str(k).capitalize()),
            'type': item.get('type'),
            'subtype': item.get('subtype'),
            'light': item.get('properties') and 'light' in item.get('properties', []),
            'two_handed': item.get('properties') and 'two_handed' in item.get('properties', []),
            'light_properties': item.get('light'),
            'proficiency_type': item.get('proficiency_type'),
            'metallic': bool(item.get('metallic')),
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

        return self.inventory[ammo_type]


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

        qty = self.inventory[ammo_type]['qty']
        self.inventory[ammo_type]['qty'] = qty + amount

    def multiattack(self, battle, npc_action):
        if not npc_action:
            return False
        if not self.class_feature("multiattack"):
            return False

        entity_state = battle.entity_state_for(self)

        if not entity_state["multiattack"]:
            return False
        if not npc_action["multiattack_group"]:
            return False

        for group, attacks in entity_state["multiattack"].items():
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

    def equipped_weapons(self):
        return [item.name for item in self.equipped_items if item.subtype == 'weapon']

    def take_damage(self, dmg: int, battle=None, critical=False):
        self.attributes["hp"] -= dmg

        if self.unconscious:
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
            self.make_dead()
            if battle and self.familiar():
                battle.remove(self)
        elif self.hp() <= 0:
            self.make_dead() if self.npc() else self.make_unconscious()
            if battle and self.familiar():
                battle.remove(self)

        if self.hp() <= 0:
            self.attributes["hp"] = 0

        if battle:
            battle.event_manager.received_event({'source': self, 'event': 'damage', 'value': dmg})
            
    def on_take_damage(self, battle, _damage_params):
        controller = battle.controller_for(self)
        if controller and hasattr(controller, 'attack_listener'):
            controller.attack_listener(battle, self)

    def eval_effect(self, effect_type, opts={}):
        if not self.has_effect(effect_type):
            return None

        active_effects = [effect for effect in self.effects[effect_type] if not effect['expiration'] or effect['expiration'] > self.session.game_time]

        if not opts.get('stacked'):
            active_effects = [active_effects[-1]] if active_effects else []

        if active_effects:
            result = opts.get('value')
            for active_effect in active_effects:
                result = active_effect['handler'].send(active_effect['method'], self, opts.merge(effect=active_effect['effect'], value=result))
            return result

        return None
    
    def make_stable(self):
        self.statuses.append("stable")
        self.death_fails = 0
        self.death_saves = 0
    
    def make_conscious(self):
        self.statuses.remove("unconscious")
        if 'stable' in self.statuses:
            self.statuses.remove("stable")
    
    def heal(self, amt):
        if self.dead():
            return

        if self.has_effect("heal_override"):
            amt = self.eval_effect("heal_override", {"heal": amt})
            
        prev_hp = self.hp()
        self.death_saves = 0
        self.death_fails = 0
        self.attributes["hp"] = min(self.max_hp(), self.hp() + amt)

        if self.hp() > 0 and amt > 0:
            if self.unconscious():
                print(f"{self.name} is now conscious because of healing and has {self.hp()} hp")
                self.conscious()
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
        roll = DieRoll.roll('1d20', description='dice_roll.death_saving_throw', entity=self, battle=battle)
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
