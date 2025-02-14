from natural20.spell.spell import Spell, consume_resource


class ExpeditiousRetreatSpell(Spell):
    def build_map(self, action):
        action = action.clone()
        return action

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session
        if item['type'] == 'expeditious_retreat':
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': session.game_time + 10 * 60
            })
            if not item['source'].current_concentration()==item['effect']:
                item['source'].concentration_on(item['effect'])
            item['target'].register_effect('dash_override', ExpeditiousRetreatSpell, effect=item['effect'], source=item['source'],
                                           duration=10 * 60)
            session.event_manager.received_event({ "event" : 'spell_buf', "spell": item['effect'], "source" : item['source'],
                                                  "target" : item['target']})

    @staticmethod
    def dash_override(entity, effect, opts=None):
        return True

    def resolve(self, entity, battle, spell_action, _battle_map):
        return [{
            'type': 'expeditious_retreat',
            'target': entity,
            'source': entity,
            'effect': self,
            'spell': self.properties
        }]
