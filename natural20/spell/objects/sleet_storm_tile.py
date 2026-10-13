"""Map tiles for the Sleet Storm spell area."""
from __future__ import annotations

import uuid

from natural20.spell.objects.zone_tile import ZoneTile


class SleetStormTile(ZoneTile):
    """Heavily obscured, difficult-terrain square of freezing sleet."""

    def __init__(self, session, battle_map, source, zone):
        self.source = source
        self.zone = zone
        self._uid = f"sleet_storm_tile:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Sleet Storm',
                'description': 'Driving freezing rain and sleet over icy ground.',
                'entity_uid': self._uid,
                'type': 'sleet_storm_tile',
                'movement_cost': 2,
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'sleet_storm': True,
                'obscuring_gas': True,
            },
        )

    def obscuring_gas_properties(self):
        return {'obscuring_gas': True}

    def token_image(self):
        return None

    def allow_targeting(self):
        return False
