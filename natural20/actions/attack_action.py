from natural20.action import Action
from natural20.die_roll import DieRoll
from natural20.entity import Entity
from natural20.item_library.common import Ground
from natural20.weapons import damage_modifier, target_advantage_condition
from natural20.utils.attack_util import after_attack_roll_hook, damage_event
from natural20.utils.ac_utils import effective_ac
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

    def second_hand(self):
        return False

    @staticmethod
    def can(entity: Entity, battle, options=None):
        if options is None:
            options = {}
        if battle and options.get('opportunity_attack'):
            return entity.total_reactions(battle) > 0

        return battle is None or entity.total_actions(battle) > 0 or entity.multiattack(battle, options.get('npc_action'))

    def __str__(self):
        if self.thrown:
            return f"{self.source} throws a {self.using} to {self.target}"
        else:
            if self.as_reaction:
                return f"{self.source} uses {self.using} as a reaction to attack {self.target}"
            else:
                return f"{self.source} attacks {self.target} with {self.using}"

    def to_dict(self):
        return {
            'action_type': self.action_type,
            'target': self.target.entity_uid if self.target else None,
            'using': self.using,
            'npc_action': self.npc_action,
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
        def set_target(target):
            def set_weapon(weapon):
                self.using = weapon
                return {
                    'param': None,
                    'next': lambda: self
                }
            self.target = target
            return {
                'param': [
                    {'type': 'select_weapon'}
                ],
                'next': set_weapon
            }
            
        return {
            'action': self,
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'weapon': self.using
                }
            ],
            'next': set_target
            
        }

    def build(session, source):
        action = AttackAction(session, source, 'attack')
        return action.build_map()
    
    def apply(battle, item, session=None):
        if 'flavor' in item and item['flavor']:
            flavor = item['flavor']
            if battle:
                battle.event_manager.received_event({'event': 'flavor', 'source': item['source'], 'target': item['target'], 'text': flavor})

        if item['type'] == 'prone':
            item['source'].prone()
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
                ground_pos = item['battle'].map.entity_or_object_pos(item['target'])
                ground_object = next((o for o in item['battle'].map.objects_at(*ground_pos) if isinstance(o, Ground)), None)
                if ground_object:
                    ground_object.add_item(item['weapon'])
        
        if item['as_reaction']:
            battle.consume(item['source'], 'reaction')
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

        attack_roll = DieRoll.roll(f"1d20+{attack_mod}", disadvantage=self.with_disadvantage(),
                                    advantage=self.with_advantage(), description='dice_roll.attack',
                                    entity=self.source, battle=battle)

        if self.source.has_effect('bless'):
            bless_roll = DieRoll.roll("1d4", description='dice_roll.bless', entity=self.source, battle=battle)
            attack_roll += bless_roll

        # print(f"{self.source.name} rolls a {attack_roll} to attack {target.name}")
        self.source.resolve_trigger('attack_resolved', {'target': target})

        if self.source.class_feature('lucky') and attack_roll.nat_1():
            attack_roll = attack_roll.reroll(lucky=True)
            # print(f"{self.source.name} uses lucky to reroll the attack roll to {attack_roll}")

        target_ac, _cover_ac = effective_ac(battle, self.source, target)

        after_attack_roll_hook(battle, target, self.source, attack_roll, target_ac)

        return self._resolve_hit(battle, target, weapon, attack_roll, damage_roll, attack_name, ammo_type, adv_info)

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
            self.result.append({
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
                'second_hand': self.second_hand(),
                'npc_action': self.npc_action
            })
            if weapon.get('on_hit'):
                for effect in weapon['on_hit']:
                    if effect.get('if') and not self.source.eval_if(effect['if'], weapon=weapon, target=target):
                        continue

                    if effect.get('save_dc'):
                        save_type, dc = effect['save_dc'].split(':')
                        if not save_type or not dc:
                            raise Exception('invalid values: save_dc should be of the form <save>:<dc>')
                        # if save_type not in Natural20.Entity.ATTRIBUTE_TYPES:
                        #     raise Exception('invalid save type')

                        save_roll = target.saving_throw(save_type, battle=battle)
                        if save_roll.result() >= int(dc):
                            if effect.get('success'):
                                self.result.append(target.apply_effect(effect['success'], battle=battle,
                                                                        flavor=effect['flavor_success']))
                        elif effect.get('fail'):
                            self.result.append(target.apply_effect(effect['fail'], battle=battle,
                                                                    flavor=effect['flavor_fail']))
                    else:
                        target.apply_effect(effect['effect'])
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
    @staticmethod
    def can(entity, battle, options=None):
        if options is None:
            options = {}
        return battle is None or (entity.total_bonus_actions(battle) > 0 and battle.two_weapon_attack(entity) and (options.get('weapon') != battle.first_hand_weapon(entity) or len([a for a in entity.equipped_weapons() if a == battle.first_hand_weapon(entity)]) >= 2))

    def second_hand(self):
        return True

    def label(self):
        return f"Bonus Action -> {super().label()}"

    def __str__(self):
        return f"TwoWeaponAttack({self.using})"
