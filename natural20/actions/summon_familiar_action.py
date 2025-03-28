from natural20.action import Action
from natural20.spell.find_familiar_spell import FindFamiliarEffect
import pdb

class SummonFamiliarAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    def clone(self):
        action = SummonFamiliarAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        return action
    
    @staticmethod
    def build(session, source):
        action = SummonFamiliarAction(session, source, "summon_familiar")
        return action.build_map()

    def build_map(self):
        def set_target(target):
            action = self.clone()
            action.target = target
            return action
        return {
            'param': [
                {
                    'type': 'select_empty_space',
                    'num': 1,
                    'range': 30
                }
            ],
            'next': set_target
        }

    @staticmethod
    def can(entity, battle, options=None):
        if battle and not entity.has_action(battle):
            return False

        # Can only summon if the entity has a familiar in their pocket dimension
        return len(entity.pocket_dimension) > 0

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        self.result.clear()

        # Get the familiar from pocket dimension
        if not self.source.pocket_dimension:
            return self

        familiar = self.source.pocket_dimension[0]

        # Create the familiar effect
        self.result.append({
            'type': 'resummon_familiar',
            'source': self.source,
            'familiar': familiar,
            'target': self.target,
            'map': map
        })

        return self

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item['type'] == 'resummon_familiar':
            battle_map = item['map']
            familiar = item['familiar']
            # Place the familiar on the map
            item['source'].pocket_dimension.remove(familiar)
            battle_map.place(item['target'], familiar)

            # Add the familiar effect
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': FindFamiliarEffect(item['source'], familiar, battle_map)
            })

            session.event_manager.received_event({
                "event": 'resummon_familiar',
                "source": item['source'],
                "target": item['target'],
                "familiar": familiar
            })

    def __str__(self):
        return f"SummonFamiliar({self.source})"

    def to_dict(self):
        return {
            'action_type': self.action_type,
            'source': self.source.entity_uid if self.source else None,
            'target': self.target
        }

    @staticmethod
    def from_dict(hash):
        action = SummonFamiliarAction(hash['source'], hash['action_type'], hash['opts'])
        action.target = hash['target']
        return action 