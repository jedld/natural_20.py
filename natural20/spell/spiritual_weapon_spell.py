from natural20.spell.spell import Spell, consume_resource
from natural20.spell.objects.spiritual_weapon import SpiritualWeapon

class SpiritualWeaponEffect:
    def __init__(self, spiritual_weapon, battle_map):
        self.spiritual_weapon = None
        self.battle_map = battle_map

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


    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item['type'] == 'spiritual_weapon':
            spiritual_weapon = SpiritualWeapon(item['source'], 'spiritual_weapon', '', {})
            battle_map = item['map']
            battle_map.place(item['target'], spiritual_weapon)

            for casted_effect in item['source'].casted_effects:
                if isinstance(casted_effect['effect'], SpiritualWeaponEffect):
                    ref_map = casted_effect['effect'].battle_map
                    casted_effect['effect'].spiritual_weapon
                    ref_map.remove(casted_effect['effect'].spiritual_weapon)

            # remove other spiritual weapon effects
            item['source'].casted_effects = [effect for effect in item['source'].casted_effects if not isinstance(effect['effect'], SpiritualWeaponEffect)]

            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': SpiritualWeaponEffect(spiritual_weapon, battle_map),
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
            'target': position,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties
        }]
