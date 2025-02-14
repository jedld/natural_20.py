from natural20.action import Action
from natural20.die_roll import DieRoll
from natural20.entity import Entity
from natural20.item_library.common import Ground
from natural20.weapons import damage_modifier, target_advantage_condition
from natural20.utils.attack_util import after_attack_roll_hook, damage_event
from natural20.utils.ac_utils import effective_ac
from natural20.spell.effects.life_drain_effect import LifeDrainEffect
import pdb

class AttackAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.using = None
        self.npc_action = None
        self.as_reaction = None
        self.thrown = None
        self.advantage_mod = None
        self.attack_roll = None
        self.as_bonus_action = False

    def second_hand(self):
        return False

    @staticmethod
    def can(entity: Entity, battle, options=None):
        if options is None:
            options = {}
        if battle and options.get('opportunity_attack'):
            return entity.total_reactions(battle) > 0

        return battle is None or entity.total_actions(battle) > 0 or entity.multiattack(battle, options.get('npc_action'))
    
    def clone(self):
        action = AttackAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        action.using = self.using
        action.npc_action = self.npc_action
        action.as_reaction = self.as_reaction
        action.thrown = self.thrown
        action.advantage_mod = self.advantage_mod
        action.attack_roll = self.attack_roll
        return action

    def __str__(self):
        weapon = self.npc_action['name'] if self.npc_action else self.using
        base_str = f"{self.source} {'throws' if self.thrown else 'uses'} {weapon}"
        target_str = f"{'at' if self.thrown else ''} on {self.target}"
        attack_roll_str = f" ({self.attack_roll} = {self.attack_roll.result()})" if self.attack_roll else ""

        full_action = f"{base_str}{target_str}"
        if self.as_reaction:
            full_action = f"{full_action} as a reaction"

        return f"{full_action}{attack_roll_str}"

    def __repr__(self):
        return f"AttackAction({self.source}, {self.action_type}, {self.opts})"

    def to_dict(self):
        return {
            'action_type': self.action_type,
            'target': self.target.entity_uid if self.target else None,
            'using': self.using,
            'npc_action': (
                self.npc_action.to_dict() 
                if self.npc_action and hasattr(self.npc_action, 'to_dict') 
                else self.npc_action
            ),
            'as_reaction': self.as_reaction,
            'thrown': self.thrown,
            'second_hand': self.second_hand()
        }

    def label(self):
        if self.npc_action:
            return self.t('action.npc_action', name=str(self.action_type), action_name=self.npc_action['name'])
        else:
            weapon = self.session.load_weapon(self.opts.get('using') or self.using)
            attack_mod = self.source.attack_roll_mod(weapon)
            i18n_token = 'action.attack_action_throw' if self.thrown else 'action.attack_action'
            return self.t(i18n_token, name=str(self.action_type), weapon_name=weapon['name'],
                     mod=f"+{attack_mod}" if attack_mod >= 0 else attack_mod,
                     dmg=damage_modifier(self.source, weapon, second_hand=self.second_hand()))

    def ranged_attack(self):
        weapon = self.get_attack_info(self.opts)
        return weapon['type'] == 'ranged_attack' or self.thrown

    def unarmed(self):
        weapon = self.get_attack_info(self.opts)
        return 'unarmed' in weapon.get('properties', [])

    def build_map(self):
        def set_weapon(weapon):
            action2 = self.clone()
            if self.source.npc():
                action2.npc_action = weapon
            else:
                action2.using = weapon
            def set_target(target):
                action = action2.clone()
                action.target = target
                return action
            return {
                'action': action2,
                'param': [
                    {
                        'type': 'select_target',
                        'num': 1,
                        'weapon': action2.using,
                        'target_types': ['enemies'],
                    }
                    ],
                'next': set_target
            }

        return {
                'param': [
                    {'type': 'select_weapon'}
                ],
                'next': set_weapon
        }

    def build(session, source):
        action = AttackAction(session, source, 'attack')
        return action.build_map()

    def apply(battle, item, session=None):
        if 'flavor' in item and item['flavor']:
            flavor = item.get('flavor', item.get('description', None))
            if battle:
                battle.event_manager.received_event({'event': 'flavor', 'source': item['source'], 'target': item.get('target', None), 'text': flavor})
        if item['type'] == 'save_success':
            battle.session.event_manager.received_event({'event': 'save_success', 'source': item['source'], 'save_type': item['save_type'], 'roll': item['roll'], 'dc': item['dc']})
        elif item['type'] == 'save_fail':
            battle.session.event_manager.received_event({'event': 'save_fail', 'source': item['source'], 'save_type': item['save_type'], 'roll': item['roll'], 'dc': item['dc']})
        elif item['type'] == 'prone':
            item['source'].prone()
        elif item['type'] == 'effect':
            if item['effect'] == 'life_drain':
                effect = LifeDrainEffect(battle, item['source'], item['context']['damage'].result())
                item['source'].register_effect('hit_point_max_override', effect, effect=effect)
                item['source'].register_event_hook('long_rest', effect)
        elif item['type'] == 'damage':
            damage_event(item, battle)
            AttackAction.consume_resource(battle, item)
        elif item['type'] == 'miss':
            AttackAction.consume_resource(battle, item)
            battle.event_manager.received_event({'attack_roll': item['attack_roll'], 'attack_name': item['attack_name'], \
                                                 'attack_thrown': item['thrown'], 'advantage_mod': item['advantage_mod'], \
                                                 'as_reaction': bool(item['as_reaction']), 'adv_info': item['adv_info'], \
                                                 'thrown': item['thrown'], \
                                                 'source': item['source'], 'target': item['target'], 'event': 'miss'})
    
    def consume_resource(battle, item):
        if item['ammo']:
            item['source'].deduct_item(item['ammo'], 1)
        
        if item['thrown']:
            if item['source'].item_count(item['weapon']) > 0:
                item['source'].deduct_item(item['weapon'], 1)
            else:
                item['source'].unequip(item['weapon'], transfer_inventory=False)
            
            if item['type'] == 'damage':
                item['target'].add_item(item['weapon'])
            else:
                ground_pos = item['battle'].entity_or_object_pos(item['target'])
                ground_object = next((o for o in item['battle'].map_for(item['source']).objects_at(*ground_pos) if isinstance(o, Ground)), None)
                if ground_object:
                    ground_object.add_item(item['weapon'])
        
        if item['as_reaction']:
            battle.consume(item['source'], 'reaction')
        elif item['as_bonus_action']:
            battle.consume(item['source'], 'bonus_action')
        elif item['second_hand']:
            battle.consume(item['source'], 'bonus_action')
        else:
            battle.consume(item['source'], 'action')
        
        item['source'].break_stealth()
        
        weapon = battle.session.load_weapon(item['weapon']) if item['weapon'] else None
        
        if weapon and 'light' in weapon.get('properties', []) and not battle.two_weapon_attack(item['source']) and not item['second_hand']:
            battle.entity_state_for(item['source'])['two_weapon'] = item['weapon']
        elif battle.entity_state_for(item['source']):
            battle.entity_state_for(item['source'])['two_weapon'] = None
        
        if battle.entity_state_for(item['source']):
            for _, attacks in battle.entity_state_for(item['source']).get('multiattack', {}).items():
                if item['attack_name'] in attacks:
                    attacks.remove(item['attack_name'])
                    if not attacks:
                        item['source'].clear_multiattack(battle)
        
        battle.dismiss_help_for(item['target'])

    def with_advantage(self):
        return self.advantage_mod > 0

    def with_disadvantage(self):
        return self.advantage_mod < 0

    def compute_hit_probability(self, battle, opts = None):
        advantage_mod, adv_info, attack_mod = self.compute_advantage_info(battle, opts)
        target_ac, _cover_ac = effective_ac(battle, self.source, self.target)

        return DieRoll.roll(f"1d20+{attack_mod}", advantage=advantage_mod > 0, disadvantage=advantage_mod < 0).prob(target_ac)

    def compute_advantage_info(self, battle, opts=None):
        if opts is None:
            opts = {}

        weapon, _, attack_mod, _, _ = self.get_weapon_info(opts)
        advantage_mod, adv_info = target_advantage_condition(battle, self.source, self.target, weapon, thrown=self.thrown)
        return advantage_mod, adv_info, attack_mod


    def avg_damage(self, battle, opts=None):
        if opts is None:
            opts = {}
        _, _, _, damage_roll, _ = self.get_weapon_info(opts)
        return DieRoll.roll(damage_roll).expected()

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        self.result.clear()
        battle = opts.get('battle')
        target = opts.get('target') or self.target
        if target is None:
            raise Exception('target is a required option for :attack')


        weapon, attack_name, attack_mod, damage_roll, ammo_type = self.get_weapon_info(opts)

        self.advantage_mod, adv_info = target_advantage_condition(battle, self.source, target, weapon, thrown=self.thrown)

        if map:
            self.evaluate_feature_protection(battle, map, target, adv_info)

        if self.attack_roll is None:
            self.attack_roll = DieRoll.roll_with_lucky(self.source, f"1d20+{attack_mod}", disadvantage=self.with_disadvantage(),
                                        advantage=self.with_advantage(), description='dice_roll.attack', battle=battle)

            if self.source.has_effect('bless'):
                bless_roll = DieRoll.roll("1d4", description='dice_roll.bless', entity=self.source, battle=battle)
                self.attack_roll += bless_roll

        # print(f"{self.source.name} rolls a {attack_roll} to attack {target.name}")
        self.source.resolve_trigger('attack_resolved', {'target': target})

        if self.source.class_feature('lucky') and self.attack_roll.nat_1():
            self.session.log_event({'event': 'lucky_reroll', 'source': self.source, 'roll': self.attack_roll})
            prev_roll = self.attack_roll
            self.attack_roll = self.attack_roll.reroll(lucky=True)
            self.session.event_manager.received_event({'event': 'lucky_reroll', 'source': self.source, 'old_roll': prev_roll, 'roll': self.attack_roll})
            # print(f"{self.source.name} uses lucky to reroll the attack roll to {attack_roll}")

        target_ac, _cover_ac = effective_ac(battle, self.source, target)

        after_attack_roll_hook(battle, target, self.source, self.attack_roll, target_ac, {'original_action': self })

        return self._resolve_hit(battle, target, weapon, self.attack_roll, damage_roll, attack_name, ammo_type, adv_info)

    def _resolve_hit(self, battle, target, weapon, attack_roll, damage_roll, attack_name, ammo_type, adv_info):
        sneak_attack_roll = None
        if self.source.class_feature('sneak_attack') and (weapon.get('properties') and 'finesse' in weapon['properties'] or weapon['type'] == 'ranged_attack') and (self.with_advantage() or (battle and battle.enemy_in_melee_range(target, [self.source]))):
            sneak_attack_roll = DieRoll.roll(self.source.sneak_attack_level(), crit=attack_roll.nat_20(),
                                                description='dice_roll.sneak_attack', entity=self.source, battle=battle)
            #  print(f"{self.source.name} rolls a {sneak_attack_roll} for sneak attack")

        damage = DieRoll.roll(damage_roll, crit=attack_roll.nat_20(), description='dice_roll.damage',
                                entity=self.source, battle=battle)

        if self.source.class_feature('great_weapon_fighting') and (weapon.get('properties') and 'two_handed' in weapon['properties'] or (weapon.get('properties') and 'versatile' in weapon['properties'] and self.source.used_hand_slots <= 1.0)):
            for i, roll in enumerate(damage.rolls):
                if roll in [1, 2]:
                    r = DieRoll.roll(f"1d{damage.die_sides}", description='dice_roll.great_weapon_fighting_reroll',
                                        entity=self.source, battle=battle)
                    battle.session.log_event({'roll': r, 'prev_roll': roll,
                                               'source': self.source, 'event': 'great_weapon_fighting_roll'})
                    damage.rolls[i] = r.result

        damage = self.check_weapon_bonuses(battle, weapon, damage, attack_roll)

        cover_ac_adjustments = 0
        hit = False
        if attack_roll.nat_20():
            hit = True
        elif attack_roll.nat_1():
            hit = False
        else:
            target_ac, cover_ac_adjustments = effective_ac(battle, self.source, target)
            hit = attack_roll.result() >= target_ac

        if damage is None:
            raise Exception('damage should is required')
        
        if hit:
            if self.source.class_feature('martial_advantage') and battle:
                for entity in battle.allies_of(self.source):
                    if entity != target and battle.map.distance(entity, target) <= 5:
                        damage += DieRoll.roll("2d6", description='dice_roll.martial_advantage', entity=self.source, battle=battle)
                        break
            hit_result = {
                'source': self.source,
                'target': target,
                'type': 'damage',
                'thrown': self.thrown,
                'weapon': self.using,
                'battle': battle,
                'advantage_mod': self.advantage_mod,
                'damage_roll': damage_roll,
                'attack_name': attack_name,
                'attack_roll': attack_roll,
                'sneak_attack': sneak_attack_roll,
                'target_ac': target.armor_class,
                'cover_ac': cover_ac_adjustments,
                'adv_info': adv_info,
                'hit?': hit,
                'damage_type': weapon['damage_type'],
                'damage': damage,
                'ammo': ammo_type,
                'as_reaction': bool(self.as_reaction),
                'as_bonus_action': bool(self.as_bonus_action),
                'second_hand': self.second_hand(),
                'npc_action': self.npc_action
            }
            self.result.append(hit_result)

            if weapon.get('on_hit'):
                print(f"Applying on_hit effects for {weapon}")
                for effect in weapon['on_hit']:
                    if effect.get('if') and not self.source.eval_if(effect['if'], {
                         "weapon": weapon, "target":target
                    }):
                        print(f"Skipping on_hit effect {effect}")
                        continue
                    if effect.get('save_dc'):
                        save_type, dc = effect['save_dc'].split(':')
                        if not save_type or not dc:
                            raise Exception('invalid values: save_dc should be of the form <save>:<dc>')
                        # if save_type not in Natural20.Entity.ATTRIBUTE_TYPES:
                        #     raise Exception('invalid save type')
                        description = effect.get('description', 'save')

                        self.result.append({
                            'type': 'flavor',
                            'source': self.source,
                            'target': target,
                            'description': description
                        })

                        save_roll = target.saving_throw(save_type, battle=battle)
                        if save_roll.result() >= int(dc):
                            self.result.append({
                                'type': 'save_success',
                                'source': target,
                                'save_type': save_type,
                                'roll': save_roll,
                                'dc': dc
                            })

                            if effect.get('success'):
                                self.result.append(target.apply_effect(effect['success'], {
                                    "battle": battle,
                                    "target": target,
                                    "flavor" : effect.get('flavor_success',None)}))
                        elif effect.get('fail'):
                            self.result.append({
                                'type': 'save_fail',
                                'source': target,
                                'save_type': save_type,
                                'roll': save_roll,
                                'dc': dc
                            })

                            self.result.append(target.apply_effect(effect['fail'], { "battle" : battle,
                                                                    "target": target,
                                                                    "damage": damage,
                                                                    "flavor": effect['flavor_fail'],
                                                                    "info" : hit_result}))
                    else:
                        target.apply_effect(effect['effect'], {"info": hit_result, "battle": battle})
        else:
            self.result.append({
                'attack_name': attack_name,
                'source': self.source,
                'target': target,
                'weapon': self.using,
                'battle': battle,
                'thrown': self.thrown,
                'type': 'miss',
                'advantage_mod': self.advantage_mod,
                'adv_info': adv_info,
                'second_hand': self.second_hand(),
                'damage_roll': damage_roll,
                'attack_roll': attack_roll,
                'as_reaction': bool(self.as_reaction),
                'as_bonus_action': bool(self.as_bonus_action),
                'target_ac': target.armor_class,
                'cover_ac': cover_ac_adjustments,
                'ammo': ammo_type,
                'npc_action': self.npc_action
            })

        return self

    def get_attack_info(self, opts=None):
        if opts is None:
            opts = {}

        npc_action = opts.get('npc_action') or self.npc_action

        using = opts.get('using') or self.using
        if using is None and npc_action is None:
            raise Exception('using or npc_action is a required option for :attack')

        if self.source.npc() and using:
            npc_action = next((a for a in self.source.npc_actions if a['name'].lower() == using.lower()), None)

        if self.source.npc():
            if npc_action is None:
                npc_action = next((action for action in self.source.properties['actions'] if action['name'].lower() == using.lower()), None)
            weapon = npc_action
        else:
            weapon = self.session.load_weapon(using)
        return weapon

    def get_weapon_info(self, opts):
        npc_action = opts.get('npc_action') or self.npc_action

        using = opts.get('using') or self.using
        if using is None and npc_action is None:
            raise Exception('using or npc_action is a required option for :attack')

        attack_name = None
        damage_roll = None
        ammo_type = None

        if self.source.npc() and using:
            npc_action = next((a for a in self.source.npc_actions if a['name'].lower() == using.lower()), None)

        if self.source.npc():
            if npc_action is None:
                npc_action = next((action for action in self.source.properties['actions'] if action['name'].lower() == using.lower()), None)

            weapon = npc_action
            attack_name = npc_action["name"]
            attack_mod = npc_action["attack"]
            damage_roll = npc_action["damage_die"]
            ammo_type = npc_action.get("ammo", None)
        else:
            weapon = self.session.load_weapon(using)
            if not weapon:
                raise Exception(f"weapon {using} not found")
            attack_name = weapon['name']
            ammo_type = weapon.get('ammo', None)
            attack_mod = self.source.attack_roll_mod(weapon)
            damage_roll = damage_modifier(self.source, weapon, second_hand=self.second_hand())

        return weapon, attack_name, attack_mod, damage_roll, ammo_type

    def evaluate_feature_protection(self, battle, map, target, adv_info):
        melee_sqaures = target.melee_squares(map, adjacent_only=True)
        for pos in melee_sqaures:
            entity = map.entity_at(*pos)
            if entity == self.source or entity == target or not entity:
                continue

            if entity.class_feature('protection') and entity.shield_equipped() and entity.has_reaction(battle):
                controller = battle.controller_for(entity)
                if hasattr(controller, 'reaction') and not controller.reaction('feature_protection', target=target,
                                                                                source=entity, attacker=self.source):
                    continue

                battle.session.event_manager.received_event({
                    "event" : 'feature_protection', "target" : target, "source": entity,
                                                        "attacker": self.source})
                _advantage, disadvantage = adv_info
                disadvantage.append('protection')
                self.advantage_mod = -1
                battle.consume(entity, 'reaction')

    def check_weapon_bonuses(self, battle, weapon, damage_roll, attack_roll):
        if weapon.get('bonus') and weapon['bonus'].get('additional') and weapon['bonus']['additional'].get('restriction') == 'nat20_attack' and attack_roll.nat_20():
            additional_damage = DieRoll.roll(weapon['bonus']['additional']['die'],
                                                description='dice_roll.special_weapon_damage', entity=self.source, battle=battle)
            damage_roll += additional_damage

        return damage_roll
    
    def to_h(self):
        return {
            "action_type": self.action_type,
            "target": self.target.entity_uid if self.target else None,
            "using": self.using,
            "npc_action": self.npc_action,
            "as_reaction": self.as_reaction,
            "thrown": self.thrown,
            "second_hand": self.second_hand()
        }


class TwoWeaponAttackAction(AttackAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)

    @staticmethod
    def can(entity, battle, options=None):
        if options is None:
            options = {}
        if not battle:
            return False

        session = options.get('session', battle.session)

        return battle and (entity.total_bonus_actions(battle) > 0 and battle.two_weapon_attack(entity) and (options.get('weapon') != battle.first_hand_weapon(entity) or len([a for a in entity.equipped_weapons(session) if a == battle.first_hand_weapon(entity)]) >= 2))

    def second_hand(self):
        return True

    def label(self):
        return f"Bonus Action -> {super().label()}"

    def __str__(self):
        return f"TwoWeaponAttack({self.using})"

class LinkedAttackAction(AttackAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)

    @staticmethod
    def can(entity, battle, options=None):
        if hasattr(entity, 'owner') and entity.owner:
            entity = entity.owner
            return super().can(entity, battle, options)

    def consume_resource(battle, item):
        if item.get('source'):
            item['source'] = item['source'].owner
        super().consume_resource(battle, item)
