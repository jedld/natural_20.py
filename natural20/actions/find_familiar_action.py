from natural20.action import Action
from natural20.entity import Entity
import pdb; 

class FindFamiliarAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        if opts is None:
            opts = {}
        self.choice = opts.get('choice', 'dismiss_temporary')

    def clone(self):
        action = FindFamiliarAction(self.session, self.source, self.action_type, self.opts)
        action.choice = self.choice
        return action
    
    @staticmethod
    def build(session, source):
        action = FindFamiliarAction(session, source, "find_familiar")
        return action.build_map()

    def build_map(self):
        def set_choice(choice):
            orig_action = self.clone()
            action = orig_action.clone()
            action.choice = choice
            return action
        return {
            'param': [
                {
                    'type': 'select_choice',
                    'choices': ['dismiss_temporary', 'dismiss_permanent']
                }
            ],
            'next': set_choice
        }

    @staticmethod
    def can(entity: Entity, battle, options=None):
        if battle and not entity.has_action(battle):
            return False
        # Can only dismiss if the entity has a familiar effect
        return any(effect['effect'].id == 'familiar' for effect in entity.casted_effects)

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        self.result.clear()

        # Find the familiar effect
        familiar_effect = next((effect for effect in self.source.casted_effects if effect['effect'].id == 'familiar'), None)
        if not familiar_effect:
            return self

        if self.choice == 'dismiss_temporary':
            self.result.append({
                'type': 'dismiss_familiar_temporary',
                'source': self.source,
                'familiar': familiar_effect['effect'].familiar,
                'effect': familiar_effect['effect']
            })
        else:
            self.result.append({
                'type': 'dismiss_familiar_permanent',
                'source': self.source,
                'familiar': familiar_effect['effect'].familiar,
                'effect': familiar_effect['effect']
            })

        return self

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item['type'] == 'dismiss_familiar_temporary':
            item['source'].pocket_dimension.append(item['familiar'])
            item['source'].remove_effect(item['effect'])
        elif item['type'] == 'dismiss_familiar_permanent':
            item['source'].remove_effect(item['effect'])

    def __str__(self):
        return f"DismissFamiliar({self.source})"

    def to_dict(self):
        return {
            'action_type': self.action_type,
            'source': self.source.entity_uid if self.source else None,
            'choice': self.choice
        }

    @staticmethod
    def from_dict(hash):
        action = FindFamiliarAction(hash['source'], hash['action_type'], hash['opts'])
        action.choice = hash['choice']
        return action 