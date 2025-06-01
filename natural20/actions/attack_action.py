from natural20.action import Action
from natural20.die_roll import DieRoll
from natural20.entity import Entity
from natural20.item_library.common import Ground
from natural20.weapons import damage_modifier, target_advantage_condition
from natural20.utils.attack_util import after_attack_roll_hook, damage_event
from natural20.utils.ac_utils import effective_ac
from natural20.spell.effects.life_drain_effect import LifeDrainEffect
from natural20.spell.effects.strength_drain_effect import StrengthDrainEffect
from natural20.spell.effects.engulf_effect import EngulfEffect
# from natural20.async_reaction_handler import AsyncReactionHandler
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
        self.hit_result = None

    def second_hand(self):
        return False

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

    @staticmethod
    def from_dict(hash):
        action = AttackAction(hash['source'], hash['action_type'], hash['opts'])
        action.target = hash['target']
        action.using = hash['using']
        action.npc_action = hash['npc_action']
        action.as_reaction = hash['as_reaction']
        action.thrown = hash['thrown']
        return action

    @staticmethod
    def can(entity: Entity, battle, options=None):
        if options is None:
            options = {}

        if entity.properties.get('spiritual'):
           entity = entity.owner

        if battle and options.get('as_bonus_action'):
            return entity.total_bonus_actions(battle) > 0

        if battle and options.get('opportunity_attack'):
            return entity.total_reactions(battle) > 0

        if battle and options.get('legendary_action'):
            return entity.total_legendary_actions(battle) > 0

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

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session
        if 'flavor' in item and item['flavor']:
            flavor = item.get('flavor', item.get('description', None))
            session.event_manager.received_event({'event': 'flavor', 'source': item['source'], 'target': item.get('target', None), 'text': flavor})
        if item['type'] == 'save_success':
            session.event_manager.received_event({'event': 'save_success', 'source': item['source'], 'save_type': item['save_type'], 'roll': item['roll'], 'dc': item['dc']})
        elif item['type'] == 'save_fail':
            session.event_manager.received_event({'event': 'save_fail', 'source': item['source'], 'save_type': item['save_type'], 'roll': item['roll'], 'dc': item['dc']})
        elif item['type'] == 'prone':
            item['source'].prone()
        elif item['type'] == 'effect':
            if item['effect'] == 'life_drain':
                effect = LifeDrainEffect(battle, item['source'], item['context']['damage'].result())
                item['source'].register_effect('hit_point_max_override', effect, effect=effect)
                item['source'].register_event_hook('long_rest', effect)
            elif item['effect'] == 'engulf':
                if not item['context'].get('source').has_casted_effect('engulf'):
                    if not item['source'].immune_to_condition('grappled'):
                        effect = EngulfEffect(session, battle, item['context']['source'], item['source'], 15, '1d8+4')
                        effect.source = item['context']['source']
                        effect.engulf(item['source'])
            elif item['effect'] == 'strength_drain':
                reduction_value = DieRoll.roll("1d4").result()
                if item['source'].strength() - reduction_value < 1:
                    item['source'].make_dead()
                else:
                    effect = StrengthDrainEffect(battle, item['source'], reduction_value)
                    item['source'].register_effect('strength_override', effect, effect=effect)
                    item['source'].register_event_hook('long_rest', effect)
                    item['source'].register_event_hook('short_rest', effect)
        elif item['type'] == 'damage':
            if item['target'].passive():
                item['target'].is_passive = False

            damage_event(item, battle)
            __class__.consume_resource(battle, item)
        elif item['type'] == 'miss':
            if item['target'].passive():
                item['target'].is_passive = False
            __class__.consume_resource(battle, item)
            session.event_manager.received_event({'attack_roll': item['attack_roll'],
                                                  'attack_name': item['attack_name'],
                                                  'attack_thrown': item['thrown'],
                                                  'advantage_mod': item['advantage_mod'],
                                                  'as_reaction': bool(item['as_reaction']),
                                                  'adv_info': item['adv_info'],
                                                  'thrown': item['thrown'],
                                                  'source': item['source'],
                                                  'target': item['target'],
                                                  'as_legendary_action': bool(item['as_legendary_action']),
                                                  'event': 'miss'})

    def consume_resource(battle, item):
        if item.get('source'):
            if item['source'].properties.get('spiritual'):
                item['source'] = item['source'].owner

        if item.get('ammo'):
            item['source'].deduct_item(item['ammo'], 1)

        if item.get('thrown'):
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

        if battle:
            if item.get('as_reaction'):
                battle.consume(item['source'], 'reaction')
            elif item.get('as_bonus_action'):
                battle.consume(item['source'], 'bonus_action')
            elif item.get('as_legendary_action'):
                battle.consume(item['source'], 'legendary_actions')
            elif item.get('second_hand'):
                battle.consume(item['source'], 'bonus_action')
            else:
                battle.consume(item['source'], 'action')

            item['source'].break_stealth()

            weapon = battle.session.load_weapon(item['weapon']) if item.get('weapon') else None

            if weapon and 'light' in weapon.get('properties', []) and not battle.two_weapon_attack(item['source']) and not item['second_hand']:
                battle.entity_state_for(item['source'])['two_weapon'] = item['weapon']
            elif battle.entity_state_for(item['source']):
                battle.entity_state_for(item['source'])['two_weapon'] = None

            state = battle.entity_state_for(item['source'])
            if state:
                for attacks in state.get('multiattack', {}).values():
                    if item['attack_name'] in attacks:
                        attacks.remove(item['attack_name'])
                        if not attacks or item['multiattack_clear']:
                            item['source'].clear_multiattack(battle)

                for attacks in state.get('multiattack_hits', {}).values():
                    if item['attack_name'] not in attacks:
                        attacks[item['attack_name']] = item['attack_name']

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
        advantage_mod, adv_info = target_advantage_condition(self.session, self.source, self.target, weapon, battle=battle, thrown=self.thrown)
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

        if self.npc_action and self.npc_action.get('force_hit'):
            self.attack_roll = None
            adv_info = [[],[]]
            self.advantage_mod = 0
        else:
            self.advantage_mod, adv_info = target_advantage_condition(session, self.source, target, weapon, battle=battle, thrown=self.thrown)

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

            _, events = after_attack_roll_hook(battle, target, self.source, self.attack_roll, target_ac, {'original_action': self })
            for event in events:
                self.result.append(event)

        return self._resolve_hit(battle, target, weapon, self.attack_roll, damage_roll, attack_name, ammo_type, adv_info)

    def _resolve_hit(self, battle, target, weapon, attack_roll, damage_roll, attack_name, ammo_type, adv_info):
        sneak_attack_roll = None
        hit = False
        if attack_roll is not None:
            if self.source.class_feature('sneak_attack') and (weapon.get('properties') and 'finesse' in weapon['properties'] or weapon['type'] == 'ranged_attack') and (self.with_advantage() or (battle and battle.enemy_in_melee_range(target, [self.source]))):
                sneak_attack_roll = DieRoll.roll(self.source.sneak_attack_level(), crit=attack_roll.nat_20(),
                                                    description='dice_roll.sneak_attack', entity=self.source, battle=battle)
        else:
            hit = True

        if damage_roll is not None:
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
        else:
            damage = DieRoll.roll("0")

        cover_ac_adjustments = 0

        if attack_roll:
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
            if not self.hit_result:
                if self.source.class_feature('martial_advantage') and battle:
                    for entity in battle.allies_of(self.source):
                        entity_map = battle.map_for(entity)
                        if entity != target and entity_map.distance(entity, target) <= 5:
                            damage += DieRoll.roll("2d6", description='dice_roll.martial_advantage', entity=self.source, battle=battle)
                            break
                self.hit_result = {
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
                    'damage_type': weapon.get('damage_type', None),
                    'damage': damage,
                    'ammo': ammo_type,
                    'as_reaction': bool(self.as_reaction),
                    'as_bonus_action': bool(self.as_bonus_action),
                    'as_legendary_action': bool(self.legendary_action),
                    'second_hand': self.second_hand(),
                    'npc_action': self.npc_action,
                    'multiattack_clear': False,
                    'multiattack_hits': True
                }

            stored_reaction = self.has_async_reaction_for_source(self.source, 'on_attack_hit')
            results = self.source.resolve_trigger('on_attack_hit', { 'result': self.hit_result, 'stored_reaction': stored_reaction } )
            if results:
                self.result.append(results)

            self.result.append(self.hit_result)
            
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

                        save_roll = target.save_throw(save_type, battle=battle)
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
                                                                    "source": self.source,
                                                                    "flavor": effect['flavor_fail'],
                                                                    "info" : self.hit_result}))
                    else:
                        self.result.append(target.apply_effect(effect['fail'], {
                                                                    "battle" : battle,
                                                                    "target": target,
                                                                    "damage": damage,
                                                                    "source": self.source,
                                                                    "flavor": effect['flavor_fail'],
                                                                    "info" : self.hit_result}))
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
                'as_legendary_action': bool(self.legendary_action),
                'target_ac': target.armor_class,
                'cover_ac': cover_ac_adjustments,
                'ammo': ammo_type,
                'npc_action': self.npc_action,
                'multiattack_clear': self.npc_action and self.npc_action.get('multiattack_clear_on_miss'),
                'multiattack_hits': False
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
            attack_mod = npc_action.get("attack", None)
            damage_roll = npc_action.get("damage_die", None)
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

    def clone(self):
        linked_attack = LinkedAttackAction(self.session, self.source, self.action_type, self.opts)
        linked_attack.npc_action = self.npc_action
        linked_attack.as_bonus_action = self.as_bonus_action
        linked_attack.as_reaction = self.as_reaction
        linked_attack.using = self.using
        linked_attack.target = self.target
        linked_attack.attack_roll = self.attack_roll
        linked_attack.result = self.result
        return linked_attack
