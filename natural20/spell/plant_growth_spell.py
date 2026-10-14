"""Plant Growth — 3rd-level transmutation (SRD).

Only the 1-action *Overgrowth* option is modelled: every square within
``radius`` (100 ft) of a point in range becomes overgrown, and moving through
it costs 4 feet per foot (tile ``movement_cost: 4``; ``Map.extra_terrain_cost``
adds the cost above the difficult-terrain doubling). The effect is permanent
and needs no concentration. The 8-hour *Enrichment* option is narrative only.
The engine doesn't track which squares hold plants, so the whole area grows.
"""
from __future__ import annotations

import uuid

from natural20.spell.objects.zone_tile import ZoneTile
from natural20.spell.spell import Spell


class OvergrowthTile(ZoneTile):
    """Permanent overgrown square (no owning zone)."""

    def __init__(self, session, battle_map, source, zone=None, movement_cost=4):
        self.source = source
        self.zone = zone
        self._uid = f"overgrowth_tile:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Overgrowth',
                'description': 'Thick, tangled plant growth.',
                'entity_uid': self._uid,
                'type': 'overgrowth_tile',
                'movement_cost': int(movement_cost),
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'overgrowth': True,
            },
        )


class PlantGrowthSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_radius',
                'num': 1,
                'range': self.properties.get('range', 150),
                'radius': self.properties.get('radius', 100),
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        center = spell_action.target
        if not isinstance(center, (list, tuple)):
            center = battle_map.entity_or_object_pos(center)
        squares = battle_map.squares_in_radius(
            (int(center[0]), int(center[1])), int(self.properties.get('radius', 100)), require_los=False)
        return [{
            'type': 'plant_growth',
            'source': entity,
            'target': [int(center[0]), int(center[1])],
            'squares': [list(s) for s in squares],
            'map': battle_map,
            'spell': self.properties,
            'effect': self,
        }]

    @staticmethod
    def plant_growth(entity, opts=None):
        return True

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'plant_growth':
            return None
        source = item['source']
        session = session or (battle.session if battle is not None else source.session)
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None
        cost = int((item.get('spell') or {}).get('overgrowth_movement_cost', 4))
        for x, y in (tuple(s) for s in item.get('squares', [])):
            if any(getattr(o, 'properties', {}).get('overgrowth') for o in battle_map.objects_at(x, y)):
                continue
            battle_map.place_object(OvergrowthTile(session, battle_map, source, movement_cost=cost), x, y)
        session.event_manager.received_event({
            'event': 'plant_growth', 'source': source, 'target': item.get('target'),
            'squares': item.get('squares', []),
        })
        return source
