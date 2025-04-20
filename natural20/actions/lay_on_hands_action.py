import types
from collections import namedtuple
from natural20.die_roll import DieRoll
from natural20.action import Action

class LayOnHandsAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.heal_amt = 0
        self.target = None

    @staticmethod
    def can(entity, battle):
        # return false if attribute second_wind_count does not exist
        if not hasattr(entity, 'lay_on_hands_max_pool'):
            return False

        return (battle is None or entity.total_actions(battle) > 0) and entity.lay_on_hands_count > 0

    def label(self):
        return 'Lay on Hands'
    
    def __str__(self):
        return f"LayOnHands"
    
    def __repr__(self):
        return f"LayOnHands"

    def build_map(self):
        def set_target(target):
            action = self.clone()
            action.target = target
            return {
                "action": action,
                "param": [
                    {
                        "type": "input",
                        "min": 1,
                        "max": self.source.lay_on_hands_pool,
                        "range": 5,
                    }
                ],
                "next": action.resolve
            }

        return {
            "action": self,
            "param": [
                {
                    "type": "select_target",
                    "range": 5,
                    "target_types": ["self", "allies"],
                    "num": 1
                }
            ],
            "next": set_target
        }

    @staticmethod
    def build(session, source):
        action = LayOnHandsAction(session, source, 'lay_on_hands')
        return action.build_map()

    def resolve(self, _session, _map, opts={}):
        heal_amt = min(self.heal_amt, self.target.max_hp - self.target.hp)
        self.result = [{
            'source': self.source,
            'target': self.target,
            'hp': heal_amt,
            'type': 'lay_on_hands',
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session
        if item['type'] == 'lay_on_hands':
            # print(f"{item['source'].name} uses Second Wind with {item['roll']} healing")
            item['source'].lay_on_hands(item['hp'])
            item['target'].heal(item['hp'])

    @staticmethod
    def describe(event):
        return f"{event['source'].name.colorize('green')} uses Second Wind with {event['roll']} healing"
