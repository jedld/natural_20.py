"""Map tiles for the Spike Growth spell area."""
from __future__ import annotations

import uuid

from natural20.spell.objects.zone_tile import ZoneTile


class SpikeGrowthTile(ZoneTile):
    """Difficult-terrain square of hidden thorns."""

    def __init__(self, session, battle_map, source, zone):
        self.source = source
        self.zone = zone
        self._uid = f"spike_growth_tile:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Spike Growth',
                'description': 'The ground bristles with hard, sharp thorns.',
                'entity_uid': self._uid,
                'type': 'spike_growth_tile',
                'movement_cost': 2,
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'spike_growth': True,
            },
        )
