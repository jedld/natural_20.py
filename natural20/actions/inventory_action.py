from dataclasses import dataclass
from natural20.action import Action

@dataclass
class InventoryAction(Action):
    @staticmethod
    def can(entity, battle):
        return True

    def build_map(self):
        return {
            'action': self,
            'param': [
                {
                    'type': 'show_inventory',
                },
            ],
            'next': lambda path: {
                'param': None,
                'next': lambda: self,
            },
        }
