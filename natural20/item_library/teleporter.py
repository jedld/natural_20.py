from natural20.item_library.object import Object
from typing import Optional
from natural20.entity import Entity
import pdb

class Teleporter(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.target_map = properties.get('target_map', None)
        self.target_position = properties['target_position']

    def on_enter(self, entity: Entity, map, battle=None):
        entity_placed = False
        if self.target_map:
            target_map = map.linked_maps.get(self.target_map)
            if target_map is None:
                # Misconfigured link (typo or map not registered in the
                # session). Don't raise — that would silently abort the move
                # loop and leave the entity stuck on the source tile. Log a
                # console event so the DM/devs can spot the bad data.
                if getattr(map, 'session', None) and getattr(map.session, 'event_manager', None):
                    map.session.event_manager.received_event({
                        "event": 'console', "target": map, "source": entity,
                        "message": (
                            f"{entity.name} stepped on {self.label()} but "
                            f"target_map '{self.target_map}' is not linked. "
                            f"Available maps: {sorted(map.linked_maps.keys())}"
                        ),
                    })
                return
            if target_map.placeable(entity, *self.target_position, squeeze=False):
                target_map.place(self.target_position, entity)
                entity_placed = True
            else:
                # look for adjacent positions
                for dx in range(-1, 2):
                    if entity_placed:
                        break
                    for dy in range(-1, 2):
                        if target_map.bidirectionally_passable(entity, self.target_position[0] + dx, self.target_position[1] + dy, self.target_position, allow_squeeze=False):
                            if target_map.placeable(entity, self.target_position[0] + dx, self.target_position[1] + dy, squeeze=False):
                                target_map.place((self.target_position[0] + dx, self.target_position[1] + dy), entity)
                                map.linked_maps[self.target_map]
                                entity_placed = True
                                break
            if entity_placed:
                # Defensive: only remove from the source map if the entity
                # is still tracked there. Another handler (or a re-entrant
                # on_enter) may have already removed it.
                if entity in getattr(map, 'entities', {}):
                    map.remove(entity)
            else:
                map.session.event_manager.received_event({
                                                        "event" : 'console', "target" : target_map, "source": entity,
                                                        "message": f"{entity.name} could not move to the target square as it is already occupied"
                                                        })

        else:
            if map.placeable(entity, *self.target_position, battle, squeeze=False):
                map.move_to(entity, *self.target_position, battle)
                entity_placed = True
        if entity_placed:
            self.resolve_trigger('activate', { "target": entity })
            try:
                from natural20.companion import sync_companions_for_entity
                game_properties = getattr(map.session, 'game_properties', None)
                if game_properties:
                    sync_companions_for_entity(map.session, game_properties, entity)
            except Exception:
                pass

    def placeable(self):
        return True

    def label(self):
        return 'ground'

    def passable(self, origin=None):
        return True

    def concealed(self):
        return False

    def jump_required(self):
        return False

    def is_visible_marker(self):
        """Whether this teleporter should be drawn with a tile-border marker
        on the web map. Configurable per-instance via the YAML key ``visible``
        (alias: ``marker``). Defaults to False so existing maps are unchanged.
        """
        props = getattr(self, 'properties', {}) or {}
        return bool(props.get('visible') or props.get('marker'))

    def marker_color(self):
        """CSS color used for the visible-teleporter border. Configurable via
        the YAML key ``marker_color``; defaults to green.
        """
        props = getattr(self, 'properties', {}) or {}
        return props.get('marker_color') or '#22c55e'

    def to_dict(self):
        hash =  super().to_dict()
        hash['target_map'] = self.target_map
        hash['target_position'] = self.target_position
        return hash
    
    @staticmethod
    def from_dict(hash):
        session = hash['session']
        teleporter = Teleporter(session, None, hash['properties'])
        teleporter.entity_uid = hash['entity_uid']
        teleporter.target_map = hash['target_map']
        teleporter.target_position = hash['target_position']
        return teleporter