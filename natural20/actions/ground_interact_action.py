from typing import List
from dataclasses import dataclass
from natural20.action import Action

@dataclass
class GroundInteractAction(Action):
    target: any
    ground_items: List[any]
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)


    @staticmethod
    def can(entity, battle):
        return battle is None or (entity.total_actions(battle) > 0 or entity.free_object_interaction(battle)) and GroundInteractAction.items_on_the_ground_count(entity, battle) > 0

    @staticmethod
    def build(session, source):
        action = GroundInteractAction(session, source, 'ground_interact')
        action.build_map()

    @staticmethod
    def items_on_the_ground_count(entity, battle):
        if battle.map is None:
            return 0

        return sum(len(items) for items in battle.map.items_on_the_ground(entity))

    def build_map(self):
        def set_ground_items(obj):
            self.ground_items = obj
            return {
                'param': None,
                'next': lambda: self
            }

        return {
            'action': self,
            'param': [
                {
                    'type': 'select_ground_items'
                }
            ],
            'next': set_ground_items
        }

    def resolve(self, session, map=None, opts=None):
        battle = opts.get('battle')

        actions = {g: {'action': 'pickup', 'items': items, 'source': self.source, 'target': g, 'battle': opts.get('battle')} for g, items in self.ground_items.items()}

        self.result.append({
            'source': self.source,
            'actions': actions,
            'map': map,
            'battle': battle,
            'type': 'pickup'
        })

        return self

    @staticmethod
    def apply(battle, item, session=None):
        entity = item['source']
        item_type = item['type']

        if item_type == 'pickup':
            for g, action in item['actions'].items():
                g.use(None, action)

            if item['cost'] == 'action':
                battle.consume(entity, 'action', 1)
            else:
                battle.consume(entity, 'free_object_interaction', 1) or battle.consume(entity, 'action', 1)
