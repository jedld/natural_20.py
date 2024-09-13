from natural20.action import Action

class FirstAidAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)


    @staticmethod
    def can(entity, battle, options=None):
        if battle is None or entity.total_actions(battle) > 0:
            return False
        unconscious_targets = FirstAidAction.unconscious_targets(entity, battle)
        return len(unconscious_targets) > 0

    @staticmethod
    def unconscious_targets(entity, battle):
        if battle is None or battle.map is None:
            return []
        
        adjacent_squares = entity.melee_squares(battle.map, adjacent_only=True)
        entities = []
        for pos in adjacent_squares:
            entity_pos = battle.map.entity_at(*pos)
            if entity_pos is None:
                continue
            if entity_pos == entity:
                continue
            if not battle.map.can_see(entity, entity_pos):
                continue
            if entity_pos.unconscious() and not entity_pos.stable() and not entity_pos.dead():
                entities.append(entity_pos)
        return entities

    def __str__(self):
        return str(self.action_type).humanize()

    def build_map(self):
        return {
            'action': self,
            'param': [
                {
                    'type': 'select_target',
                    'range': 5,
                    'target_types': ['enemies', 'allies'],
                    'filter': 'state:unconscious & state:!stable & state:!dead',
                    'num': 1
                }
            ],
            'next': lambda target: {
                'param': None,
                'next': lambda: self
            }
        }

    @staticmethod
    def build(session, source):
        action = FirstAidAction(session, source, 'grapple')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        target = opts['target'] if opts and 'target' in opts else self.target
        battle = opts['battle'] if opts and 'battle' in opts else None
        if target is None:
            raise Exception('target is a required option for :first_aid')

        medicine_check = self.source.medicine_check(battle)

        if medicine_check.result >= 10:
            self.result = [{
                'source': self.source,
                'target': target,
                'type': 'first_aid',
                'success': True,
                'battle': battle,
                'roll': medicine_check
            }]
        else:
            self.result = [{
                'source': self.source,
                'target': target,
                'type': 'first_aid',
                'success': False,
                'battle': battle,
                'roll': medicine_check
            }]

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'first_aid':
            if item['success']:
                item['target'].stable()
                battle.event_manager.received_event({ "event" : 'first_aid',
                                                      "target": item['target'],
                                                      "source": item['source'],
                                                      "roll" : item['roll'] })
            else:
                battle.event_manager.received_event({ "event" : 'first_aid_failure',
                                                      "target" : item['target'],
                                                      "source" : item['source'],
                                                      "roll" : item['roll'] })

            battle.consume(item['source'], 'action')
