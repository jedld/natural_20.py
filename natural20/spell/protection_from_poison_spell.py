from natural20.spell.spell import Spell
class ProtectionFromPoisonSpell(Spell):
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
                    'unique_targets': True,
                    'target_types': ['allies', 'self']
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
                'type': 'protection_from_poison',
                'spell': self.properties,
                'effect': self
            })
        return results

    @staticmethod
    def resistance_override(entity, opt=None):
        if opt is None:
            opt = {}

        resistances = opt.get('value')
        if 'poison' in resistances:
            resistances.add('poison')

        return resistances

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session
        if item['type'] == 'protection_from_poison':
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': session.game_time + 10
            })

            if item['target'].has_effect('protection_from_poison'):
                item['target'].remove_effect('protection_from_poison')

            item['target'].register_effect('protection_from_poison', ProtectionFromPoisonSpell, effect=item['effect'],
                                       source=item['source'],
                                       duration=10)

            if 'poisoned' in item['target'].statuses:
                item['source'].statuses.remove('poisoned')

            session.event_manager.received_event({"event" : 'spell_buf',
                                                  "spell" : item['effect'],
                                                  "source": item['source'],
                                                  "target" : item['target'] })
            return item['target']