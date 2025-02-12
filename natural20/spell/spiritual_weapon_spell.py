from natural20.spell.spell import Spell, consume_resource
from natural20.spell.objects.spiritual_weapon import SpiritualWeapon

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
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': session.game_time + 60
            })

            spiritual_weapon = SpiritualWeapon('spiritual_weapon', '', {})
            battle_map = item['map']
            battle_map.place(item['target'], spiritual_weapon)

            session.event_manager.received_event({"event" : 'spiritual_weapon',
                                                  "spell" : item['effect'],
                                                  "source": item['source'],
                                                  "target" : item['target'] })




    def resolve(self, entity, battle, spell_action):
        battle_map, position = spell_action.target
        return [{
            'type': 'spiritual_weapon',
            'map': battle_map,
            'target': position,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties
        }]
