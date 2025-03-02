from natural20.die_roll import DieRoll
from natural20.item_library.object import Object

class Note(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.properties = properties

    def build_map(self, action, action_object):
        return action_object

