from natural20.spell.spell import Spell, consume_resource
from natural20.spell.objects.spiritual_weapon import SpiritualWeapon
from natural20.map import Map
import pdb
class SpiritualWeaponEffect:
    def __init__(self, source, spiritual_weapon, battle_map):
        self.source = source
        self.spiritual_weapon = spiritual_weapon
        self.battle_map = battle_map

    @property
    def id(self):
        return 'spiritual_weapon'
    
    def dismiss(self, entity, effect):
        self.battle_map.remove(self.spiritual_weapon)
class SpiritualWeaponSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        return {
            'param': [
                {
                    'type': 'select_empty_space',
                    'num': 1,
                    'range': 60
                }
            ],
            'next': set_target
        }

    def validate(self, battle_map: Map, target=None):
        super().validate(target)
        if target is None:
            target = self.target

        self.errors = []
        if not target:
            self.errors.append("Invalid target")

        if target and (not isinstance(target, tuple) and not isinstance(target, list)) or len(target) != 2:
            self.errors.append("Invalid target type, should be a position")
            return

        # target must be empty space
        if target and not battle_map.placeable(SpiritualWeapon(None, self.source, 'spiritual_weapon', '', {}), *target):
            self.errors.append("Target must be empty space")

        if target and not battle_map.distance_to_square(self.source, *target) < 60:
            self.errors.append("Target is out of range")

        if target and not battle_map.can_see_square(self.source, target):
            self.errors.append("Target is not visible")

        return len(self.errors) == 0

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item['type'] == 'spiritual_weapon':
            # remove other spiritual weapon effects
            item['source'].remove_effect('spiritual_weapon')
            damage_die = 1

            if item['level'] > 2:
                damage_die += (item['level'] - 2) // 2

            spell_casting_modifier = item['source'].cleric_spell_casting_modifier()
            attributes = {
            }
            spiritual_weapon = SpiritualWeapon(session, item['source'],
                                               'spiritual_weapon', '', attributes,
                                               damage=f"{damage_die}d8+{spell_casting_modifier}",
                                               spell=item['spell'])

            battle_map = item['map']
            battle_map.place(item['target'], spiritual_weapon)
            if battle:
                battle.entities[spiritual_weapon] = {
                    'movement': 20,
                    'action': 0,
                    'bonus_action': 0,
                    'reaction': 0,
                    'free_object_interaction': 0,
                    'active_perception': 0,
                    'active_perception_disadvantage': 0,
                    'two_weapon': None,
                    'action_surge': None,
                    'casted_level_spells': [],
                    'positions_entered': {},
                    'group': battle.group_for(item['source'])
                }

            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': SpiritualWeaponEffect(item['source'], spiritual_weapon, battle_map),
                'expiration': session.game_time + 60
            })

            session.event_manager.received_event({"event" : 'spiritual_weapon',
                                                  "spell" : item['effect'],
                                                  "source": item['source'],
                                                  "target" : item['target'] })




    def resolve(self, entity, battle, spell_action, battle_map):
        position = spell_action.target
        return [{
            'type': 'spiritual_weapon',
            'map': battle_map,
            'level': spell_action.at_level,
            'target': position,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties
        }]
