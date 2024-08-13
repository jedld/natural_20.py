from natural20.spell.spell import Spell, consume_resource

class MageArmorSpell(Spell):
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

    def validate(self, action):
        action.errors.clear()
        if action.target.wearing_armor():
            action.errors.append('wearing_armor')

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'mage_armor':
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': battle.session.game_time + 8 * 60 * 60
            })
            item['target'].register_effect('ac_override', MageArmorSpell, effect=item['effect'], source=item['source'],
                                           duration=8 * 60 * 60)
            item['target'].register_event_hook('equip', MageArmorSpell, effect=item['effect'],
                                               source=item['source'],
                                               duration=8 * 60 * 60)
            battle.event_manager.received_event({ "event" : 'spell_buf',
                                                  "spell" : item['effect'],
                                                  "source": item['source'],
                                                  "target" : item['target'] })


    @staticmethod
    def ac_override(entity, effect):
        return 13 + entity.dex_mod()

    @staticmethod
    def equip(entity, opts=None):
        if entity.wearing_armor():
            entity.dismiss_effect(opts['effect'])

    def resolve(self, entity, battle, spell_action):
        return [{
            'type': 'mage_armor',
            'target': spell_action.target,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties
        }]
