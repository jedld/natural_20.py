from natural20.actions.attack_action import AttackAction
from natural20.die_roll import DieRoll
from natural20.utils.attack_util import damage_event
from natural20.spell.spell import Spell


class BoomingBladeRider:
    def __init__(self, source, target, dice, spell_properties):
        self.source = source
        self.target = target
        self.dice = dice
        self.spell_properties = spell_properties
        self.battle = None
        self.active = True

    def movement(self, battle, source, opt=None):
        if not self.active:
            return
        if source != self.target:
            return
        move_path = (opt or {}).get('move_path') or []
        if len(move_path) < 2 or move_path[0] == move_path[-1]:
            return

        damage_roll = DieRoll.roll(
            f'{self.dice}d8',
            battle=battle,
            entity=self.source,
            description='dice_roll.spells.generic_damage'
        )
        damage_event({
            'source': self.source,
            'target': self.target,
            'attack_name': self.spell_properties.get('name', 'Booming Blade'),
            'damage_type': self.spell_properties.get('damage_type', 'thunder'),
            'attack_roll': None,
            'damage_roll': damage_roll,
            'advantage_mod': None,
            'adv_info': None,
            'damage': damage_roll,
            'spell': self.spell_properties,
        }, battle)
        self.dismiss(self.source, {'battle': battle, 'remove_handler': False})

    def dismiss(self, _entity=None, opt=None):
        opt = opt or {}
        self.active = False
        battle = opt.get('battle') or self.battle
        if battle and opt.get('remove_handler', True):
            handlers = battle.battle_field_events.get('movement', {})
            handlers.pop(self, None)
        if self.target and 'booming_blade' in self.target.statuses:
            self.target.statuses.remove('booming_blade')


class BoomingBladeSpell(Spell):
    def build_map(self, orig_action):
        def set_weapon(weapon):
            action_with_weapon = orig_action.clone()
            action_with_weapon.using = weapon

            def set_target(target):
                action = action_with_weapon.clone()
                action.target = target
                return action

            return {
                'action': action_with_weapon,
                'param': [
                    {
                        'type': 'select_target',
                        'num': 1,
                        'weapon': weapon,
                        'range': self.properties.get('range', 5),
                        'target_types': ['enemies', 'objects'],
                    }
                ],
                'next': set_target
            }

        return {
            'param': [
                {
                    'type': 'select_weapon',
                    'valid_weapon_types': ['melee_attack'],
                }
            ],
            'next': set_weapon
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        weapon_id = getattr(spell_action, 'using', None)
        if not weapon_id:
            equipped = entity.equipped_weapons(
                self.session,
                valid_weapon_types=['melee_attack']
            )
            weapon_id = equipped[0] if equipped else None
        if not weapon_id:
            raise ValueError('Booming Blade requires a melee weapon')

        attack = AttackAction(self.session, entity, 'attack')
        attack.using = weapon_id
        attack.target = target
        attack.resolve(self.session, battle_map, {'battle': battle})

        result = []
        hit = False
        attack_roll = None
        for item in attack.result:
            if item.get('type') == 'damage':
                # The spell consumes the action; the embedded weapon strike
                # should not charge action economy a second time.
                item['_free_attack'] = True
                hit = True
                attack_roll = item.get('attack_roll')
            result.append(item)

        thunder_dice = self._hit_thunder_dice(entity)
        if hit and thunder_dice > 0:
            thunder_roll = DieRoll.roll(
                f'{thunder_dice}d8',
                crit=bool(attack_roll and attack_roll.nat_20()),
                battle=battle,
                entity=entity,
                description=self.t(
                    'dice_roll.spells.generic_damage',
                    spell=self.t('spell.booming_blade')
                )
            )
            result.append({
                'source': entity,
                'target': target,
                'attack_name': self.properties.get('name', 'Booming Blade'),
                'damage_type': self.properties.get('damage_type', 'thunder'),
                'attack_roll': attack_roll,
                'damage_roll': thunder_roll,
                'advantage_mod': getattr(attack, 'advantage_mod', None),
                'adv_info': None,
                'damage': thunder_roll,
                'cover_ac': 0,
                'type': 'spell_damage',
                'spell': self.properties,
            })
        if hit:
            result.append({
                'source': entity,
                'target': target,
                'type': 'booming_blade_rider',
                'effect': BoomingBladeRider(
                    entity,
                    target,
                    self._movement_thunder_dice(entity),
                    self.properties
                )
            })

        return result

    def _hit_thunder_dice(self, entity):
        level = entity.level()
        if level >= 17:
            return 3
        if level >= 11:
            return 2
        if level >= 5:
            return 1
        return 0

    def _movement_thunder_dice(self, entity):
        return self._hit_thunder_dice(entity) + 1

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'booming_blade_rider':
            return None
        effect = item['effect']
        target = item['target']
        if battle:
            effect.battle = battle
            battle.battle_field_events.setdefault('movement', {})[effect] = 'movement'
        if 'booming_blade' not in target.statuses:
            target.statuses.append('booming_blade')
        item['source'].register_event_hook(
            'start_of_turn',
            effect,
            method_name='dismiss',
            effect=effect,
            source=item['source']
        )
        return None
