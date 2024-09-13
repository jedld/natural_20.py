import natural20.controller as controller
from natural20.generic_controller import GenericController

class ManualControl(Exception):
    pass

class WebController(GenericController):
    def __init__(self, session, user, sid = None):
        super().__init__(session)
        self.user = user
        self.sids = []

    def add_sid(self, sid):
        self.sids.append(sid)

    def roll_for(self, entity, die_type, number_of_times, description, advantage=False, disadvantage=False):
        pass

    def move_for(self, entity, battle):
        # raise exception to return back to the webapp
        raise ManualControl()
