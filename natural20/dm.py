from natural20.entity import Entity


class DungeonMaster(Entity):
    """Stand-in entity for DM-driven interactions; uses a string uid like PCs/NPCs from data."""

    DM_ENTITY_UID = 'dungeon_master'

    def __init__(self, session, name, opt=None):
        super().__init__(name, "dm", {})
        self.entity_uid = self.DM_ENTITY_UID
        self.session = session
        self.inventory = []
        self.properties = {}
        self.is_admin = True

    def launguages(self):
        return ['all']