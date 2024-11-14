from natural20.spell.spell import Spell, consume_resource

class ShieldOfFaithSpell(Spell):
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
                    'type': 'select_target',
                    'num': 1,
                    'range': 5,
                    'target_types': ['allies', 'self']
                }
            ],
            'next': set_target
        }


    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session
        if item['type'] == 'shield_of_faith':
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': session.game_time + 8 * 60 * 60
            })

            if not item['source'].current_concentration()==item['effect']:
                item['source'].concentration_on(item['effect'])

            item['target'].register_effect('ac_bonus', ShieldOfFaithSpell, effect=item['effect'], source=item['source'],
                                           duration=8 * 60 * 60)

            session.event_manager.received_event({"event" : 'spell_buf',
                                                  "spell" : item['effect'],
                                                  "source": item['source'],
                                                  "target" : item['target'] })


    @staticmethod
    def ac_bonus(entity, effect):
        return 2


    def resolve(self, entity, battle, spell_action):
        return [{
            'type': 'shield_of_faith',
            'target': spell_action.target,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties
        }]
