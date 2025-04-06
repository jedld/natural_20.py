from natural20.spell.spell import Spell
class BlessSpell(Spell):
    def __init__(self, session, source, spell_name, details):
            super().__init__(session, source, spell_name, details)

    def to_dict(self):
        return {
            'name': self.name,
            'action': self.action,
            'session': self.session,
            'properties': self.properties,
            'source': self.source.entity_uid,
        }

    @staticmethod
    def from_dict(data):
        bless_spell = BlessSpell(data['session'], data['source'], data['name'], data['properties'])
        bless_spell.action = data['action']
        return bless_spell

    def build_map(self, orig_action):
        additional_targets = 0
        if orig_action.at_level > 1:
            additional_targets = orig_action.at_level - 1

        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 3 + additional_targets,
                    'range': 30,
                    'unique_targets': True,
                    'target_types': ['allies']
                }
            ],
            'next': set_target
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        targets = spell_action.target
        results = []
        if not isinstance(targets, list):
            targets = [targets]
        for target in targets:
            results.append({
                'source': entity,
                'target': target,
                'type': 'bless',
                'spell': self.properties,
                'effect': self
            })
        return results

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session
        if item['type'] == 'bless':
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': session.game_time + 60
            })

            if not item['source'].current_concentration()==item['effect']:
                item['source'].concentration_on(item['effect'])

            item['target'].register_effect('bless', BlessSpell, effect=item['effect'], source=item['source'], duration=60)
            session.event_manager.received_event({ "event" : 'spell_buf',
                                                  "spell" : item['effect'],
                                                  "source": item['source'],
                                                  "target" : item['target'] })
            return item['target']