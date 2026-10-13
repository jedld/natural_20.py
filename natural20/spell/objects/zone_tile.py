"""Base class for terrain squares owned by a persistent spell zone."""
from __future__ import annotations

from natural20.item_library.object import Object


class ZoneTile(Object):
    """Invisible placeable marker for one square of a ``PersistentAoEZone``.

    Subclasses take ``(session, battle_map, source, zone)``. Save/load stores
    only identity, properties, the source uid and the zone; the zone and source
    are relinked by ``relink_persistent_zones``.
    """

    def token_image(self):
        return None

    def allow_targeting(self):
        return False

    def to_dict(self):
        return {
            'session': self.session,
            'entity_uid': self.entity_uid,
            'properties': dict(self.properties or {}),
            'source': getattr(self.source, 'entity_uid', self.source),
            'zone': self.zone,
        }

    @classmethod
    def from_dict(cls, data):
        tile = cls.__new__(cls)
        properties = dict(data.get('properties') or {})
        properties['entity_uid'] = data.get('entity_uid') or properties.get('entity_uid')
        tile.source = data.get('source')
        tile.zone = data.get('zone')
        tile._uid = properties['entity_uid']
        seed = properties.get('grease_seed') or properties.get('stinking_cloud_seed')
        if seed:
            tile._seed = seed
        Object.__init__(tile, data.get('session'), None, properties)
        return tile
