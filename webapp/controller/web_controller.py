import natural20.controller as controller
from natural20.generic_controller import GenericController

class ManualControl(Exception):
    pass

class WebController(GenericController):
    def __init__(self, session, user, sid = None):
        super().__init__(session)
        self.users = set()
        self.sids = []
        self.users.add(user)

    def add_sid(self, sid):
        self.sids.append(sid)

    def add_user(self, user):
        self.users.add(user)

    def get_users(self):
        return self.users

    def roll_for(self, entity, die_type, number_of_times, description, advantage=False, disadvantage=False):
        pass

    def move_for(self, entity, battle):
        # raise exception to return back to the webapp
        raise ManualControl()
    
    def opportunity_attack_listener(self, battle, session, entity, map, event):
        self.reaction = event
        actions = [s for s in entity.available_actions(session, battle, opportunity_attack=True)]

        valid_actions = []
        for action in actions:
            valid_targets = battle.valid_targets_for(entity, action)
            if event['target'] in valid_targets:
                action.target = event['target']
                action.as_reaction = True
                valid_actions.append(action)

        yield battle, entity, valid_actions
