"""Map tiles for the Silence spell area."""
from __future__ import annotations

import uuid

from natural20.spell.objects.zone_tile import ZoneTile


class SilenceTile(ZoneTile):
    """Square inside a sphere of magical silence (``silenced: true``)."""

    def __init__(self, session, battle_map, source, zone):
        self.source = source
        self.zone = zone
        self._uid = f"silence_tile:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Silence',
                'description': 'No sound can be created within or pass through this area.',
                'entity_uid': self._uid,
                'type': 'silence_tile',
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'silenced': True,
            },
        )
