from natural20.entity import Entity

class DungeonMaster(Entity):
    def __init__(self, session, name, opt=None):
        super().__init__(name, "dm", {})
        self.session = session
        self.inventory = []
        self.properties = {}
        self.is_admin = True

    def launguages(self):
        return ['all']