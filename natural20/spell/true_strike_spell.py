"""True Strike — 2014 concentration advantage cantrip, or 2024 weapon attack cantrip."""

from natural20.actions.attack_action import AttackAction
from natural20.die_roll import DieRoll
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell


class TrueStrikeSpell(Spell):
    def _is_2024(self, entity=None):
        session = getattr(entity, 'session', None) or getattr(self, 'session', None)
        ruleset = getattr(session, 'ruleset', None) if session is not None else None
        return bool(ruleset and ruleset.name == '5e-2024')

    def build_map(self, orig_action):
        if not self._is_2024(getattr(orig_action, 'source', None) or self.source):
            return self._build_map_2014(orig_action)
        return self._build_map_2024(orig_action)

    def _build_map_2014(self, orig_action):
        def set_target(target):
            if not target:
                raise ValueError("Invalid target")
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties.get('range', 30),
                    'target_types': ['enemies'],
                },
            ],
            'next': set_target,
        }

    def _build_map_2024(self, orig_action):
        def set_weapon(weapon):
            action_with_weapon = orig_action.clone()
            action_with_weapon.using = weapon

            def set_damage_type(choice):
                damage_type = str(choice).lower()
                action = action_with_weapon.clone()
                action.spell_action.chosen_damage_type = damage_type

                def set_target(target):
                    action2 = action.clone()
                    action2.target = target
                    return action2

                weapon_meta = self.session.load_weapon(weapon) or {}
                range_ft = weapon_meta.get('range', 5)
                if weapon_meta.get('type') == 'ranged_attack':
                    range_ft = weapon_meta.get('range_max') or weapon_meta.get('range', 30)
                return {
                    'param': [
                        {
                            'type': 'select_target',
                            'num': 1,
                            'weapon': weapon,
                            'range': range_ft,
                            'target_types': ['enemies', 'objects'],
                        }
                    ],
                    'next': set_target,
                }

            return {
                'param': [
                    {
                        'type': 'select_choice',
                        'choices': [
                            ['Weapon damage', 'weapon'],
                            ['Radiant', 'radiant'],
                        ],
                        'num': 1,
                    }
                ],
                'next': set_damage_type,
            }

        return {
            'param': [
                {
                    'type': 'select_weapon',
                    'valid_weapon_types': ['melee_attack', 'ranged_attack'],
                }
            ],
            'next': set_weapon,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        if self._is_2024(entity):
            return self._resolve_2024(entity, battle, spell_action, battle_map)
        return self._resolve_2014(entity, battle, spell_action, battle_map)

    def _resolve_2014(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        return [{
            'source': entity,
            'target': target,
            'type': 'true_strike',
            'effect': self,
        }]

    def _resolve_2024(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        weapon_id = getattr(spell_action, 'using', None)
        if not weapon_id:
            equipped = entity.equipped_weapons(
                self.session,
                valid_weapon_types=['melee_attack', 'ranged_attack'],
            )
            weapon_id = equipped[0] if equipped else None
        if not weapon_id:
            raise ValueError('True Strike requires a weapon')

        ability = HoldPersonSpell._caster_spell_ability(entity, spell_action)
        # Map short names (int/wis/cha) if class uses those
        ability_map = {
            'strength': 'str', 'dexterity': 'dex', 'constitution': 'con',
            'intelligence': 'int', 'wisdom': 'wis', 'charisma': 'cha',
            'str': 'str', 'dex': 'dex', 'con': 'con',
            'int': 'int', 'wis': 'wis', 'cha': 'cha',
        }
        ability = ability_map.get(str(ability).lower(), 'int')

        prev = getattr(entity, '_spellcasting_attack_ability_override', None)
        entity._spellcasting_attack_ability_override = ability
        try:
            attack = AttackAction(self.session, entity, 'attack')
            attack.using = weapon_id
            attack.target = target
            attack.resolve(self.session, battle_map, {'battle': battle})
        finally:
            entity._spellcasting_attack_ability_override = prev

        result = []
        hit = False
        attack_roll = None
        damage_type_choice = getattr(
            getattr(spell_action, 'spell_action', None),
            'chosen_damage_type',
            'weapon',
        )
        for item in attack.result:
            if item.get('type') == 'damage':
                item['_free_attack'] = True
                hit = True
                attack_roll = item.get('attack_roll')
                if damage_type_choice == 'radiant':
                    item['damage_type'] = 'radiant'
            result.append(item)

        extra = self._cantrip_radiant_dice(entity)
        if hit and extra > 0:
            radiant = DieRoll.roll(
                f'{extra}d6',
                crit=bool(attack_roll and attack_roll.nat_20()),
                battle=battle,
                entity=entity,
                description='dice_roll.spells.true_strike',
            )
            result.append({
                'source': entity,
                'target': target,
                'attack_name': self.properties.get('name', 'True Strike'),
                'damage_type': 'radiant',
                'attack_roll': attack_roll,
                'damage_roll': radiant,
                'damage': radiant,
                'type': 'spell_damage',
                'spell': self.properties,
            })
        return result

    def _cantrip_radiant_dice(self, entity):
        level = entity.level() if hasattr(entity, 'level') else 1
        if callable(level):
            level = level()
        level = int(level or 1)
        if level >= 17:
            return 3
        if level >= 11:
            return 2
        if level >= 5:
            return 1
        return 0

    def start_of_turn(self, entity, opt=None):
        self.action.target.register_effect(
            'targeted_advantage_override', self, effect=self, source=entity
        )
        entity.register_event_hook('end_of_turn', self, effect=self)
        self.action.target.register_event_hook('after_attack_roll_target', self, effect=self)

    def end_of_turn(self, entity, opt=None):
        entity.dismiss_effect(self)

    def targeted_advantage_override(self, entity, opt=None):
        return [['true_strike_advantage'], []]

    def after_attack_roll_target(self, entity, opt=None):
        if entity == self.action.target:
            return [{
                'type': 'dismiss_effect',
                'source': self.action.source,
                'target': self.action.target,
                'effect': self,
            }]
        return []

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'true_strike':
            return
        if not item['source'].current_concentration() == item['effect']:
            item['source'].concentration_on(item['effect'])
        item['source'].add_casted_effect({
            "target": item['target'],
            "effect": item['effect'],
        })

        if battle:
            item['source'].register_event_hook(
                'start_of_turn', item['effect'], effect=item['effect']
            )
        else:
            item['target'].register_effect(
                'targeted_advantage_override', item['effect'],
                effect=item['effect'], source=item['source'],
            )
            item['source'].register_event_hook(
                'end_of_turn', item['effect'], effect=item['effect']
            )
            item['target'].register_event_hook(
                'after_attack_roll_target', item['effect'], effect=item['effect']
            )
