"""Map marker for the Flaming Sphere spell."""
from __future__ import annotations

import uuid

from natural20.spell.objects.zone_tile import ZoneTile


class FlamingSphereTile(ZoneTile):
    """The 5-foot sphere of fire itself (one square)."""

    def __init__(self, session, battle_map, source, zone):
        self.source = source
        self.zone = zone
        self._uid = f"flaming_sphere:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Flaming Sphere',
                'description': 'A 5-foot sphere of roaring flame.',
                'entity_uid': self._uid,
                'type': 'flaming_sphere',
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'flaming_sphere': True,
            },
        )
