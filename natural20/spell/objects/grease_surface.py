import uuid

from natural20.item_library.object import Object


class GreaseSurface(Object):
    """Invisible placeable terrain object used for Grease difficult terrain.

    Rendering is handled procedurally by the web UI via marker metadata,
    not via an image asset.
    """

    def __init__(self, session, battle_map, source, zone):
        self.source = source
        self.zone = zone
        self._uid = f"grease_surface:{uuid.uuid4()}"
        self._seed = self._uid.split(':', 1)[1][:10]
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Grease',
                'description': 'A patch of slippery grease.',
                'entity_uid': self._uid,
                'type': 'grease_surface',
                'movement_cost': 2,
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'grease_surface': True,
                'grease_seed': self._seed,
            },
        )

    def token_image(self):
        return None

    def allow_targeting(self):
        return False

    def on_enter(self, entity, map_obj, battle, from_pos=None, to_pos=None):
        if self.zone is None:
            return
        if from_pos is not None and self.zone.contains(from_pos):
            return
        self.zone.apply_save(entity, reason='enter')
