"""Map marker for a hovering dancing weapon (item YAML ``dancing``)."""
from __future__ import annotations

import uuid

from natural20.spell.objects.zone_tile import ZoneTile


class DancingWeaponTile(ZoneTile):
    """Passable marker for the square a dancing weapon hovers over.

    Saved through the generic ``!zone_tile`` tag with no zone; the wielder's
    ``dancing_weapons`` property holds the game state and points here by uid.
    """

    def __init__(self, session, battle_map, source, item_key, item_name=None, image=None):
        self.source = source
        self.zone = None
        self._uid = f"dancing_weapon:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': item_name or str(item_key).replace('_', ' ').title(),
                'description': 'A sword hovering in the air, fighting on its own.',
                'entity_uid': self._uid,
                'type': 'dancing_weapon',
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'dancing_weapon': True,
                'item': item_key,
                'item_image': image or item_key,
                'owner_uid': getattr(source, 'entity_uid', source),
            },
        )

    def token_image(self):
        return f"items/{self.properties.get('item_image') or self.properties.get('item')}.png"
