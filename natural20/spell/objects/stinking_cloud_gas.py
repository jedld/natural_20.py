"""Map tiles for the Stinking Cloud spell area."""
from __future__ import annotations

import uuid

from natural20.item_library.object import Object


class StinkingCloudGas(Object):
    """Invisible terrain marker for a single square of Stinking Cloud."""

    def __init__(self, session, battle_map, source, zone, *, seed=None):
        self.source = source
        self.zone = zone
        self._uid = f"stinking_cloud_gas:{uuid.uuid4()}"
        self._seed = seed or self._uid.split(':', 1)[1][:10]
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Stinking Cloud',
                'description': 'A nauseating cloud of yellow gas.',
                'entity_uid': self._uid,
                'type': 'stinking_cloud_gas',
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'stinking_cloud_gas': True,
                'obscuring_gas': True,
                'stinking_cloud_seed': self._seed,
            },
        )

    def obscuring_gas_properties(self):
        return {'obscuring_gas': True}

    def token_image(self):
        return None

    def allow_targeting(self):
        return False
