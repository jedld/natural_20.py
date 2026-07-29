from natural20.item_library.object import Object
from typing import Optional
from natural20.entity import Entity


class Teleporter(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.target_map = properties.get('target_map', None)
        self.target_position = properties.get('target_position', [0, 0])

    def _session_gate_allows(self, entity: Entity, map) -> bool:
        """Optional campaign gate via ``requires_session`` on the teleporter.

        YAML shapes supported::

            requires_session:
              all_of: [flag_a, flag_b]
              # and / or
              any_of: [flag_a, flag_b, flag_c]
              min_count: 2   # how many of any_of must be truthy (default 1)
              bypass_any: [ophelia_invitation]  # any one of these alone opens

            # Optional: carrying listed item types counts toward any_of hits
            # (one point per distinct item type present in inventory/equipment).
            inventory_proofs: [black_rose_pin]

        Legacy alias: ``visibility_flag: some_flag`` (treated as all_of: [some_flag]).
        """
        props = getattr(self, 'properties', {}) or {}
        req = props.get('requires_session')
        legacy = props.get('visibility_flag')
        if not req and not legacy:
            return True

        session = getattr(map, 'session', None) or getattr(self, 'session', None)
        state = getattr(session, 'session_state', {}) or {} if session else {}
        if not isinstance(state, dict):
            state = {}

        if legacy and not req:
            req = {'all_of': [legacy]}

        bypass_any = list(req.get('bypass_any') or [])
        for flag in bypass_any:
            if state.get(flag):
                return True

        all_of = list(req.get('all_of') or [])
        any_of = list(req.get('any_of') or [])
        min_count = int(req.get('min_count', 1 if any_of else 0))

        for flag in all_of:
            if not state.get(flag):
                return False

        hits = 0
        if any_of:
            hits = sum(1 for flag in any_of if state.get(flag))

        inventory_proofs = list(req.get('inventory_proofs') or props.get('inventory_proofs') or [])
        if inventory_proofs and entity is not None:
            carried = set()
            try:
                inv = getattr(entity, 'inventory', None) or {}
                if isinstance(inv, dict):
                    for key, val in inv.items():
                        qty = val.get('qty', 1) if isinstance(val, dict) else val
                        if qty:
                            carried.add(str(key))
                equipped = getattr(entity, 'equipped_items', None) or getattr(entity, 'equipped', None) or []
                for item in equipped:
                    if isinstance(item, str):
                        carried.add(item)
                    elif isinstance(item, dict) and item.get('type'):
                        carried.add(str(item['type']))
                    elif hasattr(item, 'name'):
                        carried.add(str(item.name))
            except Exception:
                carried = set()
            for item_type in inventory_proofs:
                if str(item_type) in carried:
                    hits += 1

        if any_of or inventory_proofs:
            if hits < min_count:
                return False

        return True

    def _deny_entry(self, entity: Entity, map) -> None:
        props = getattr(self, 'properties', {}) or {}
        message = props.get('deny_message') or (
            f"{entity.name} cannot use {self.label()} yet — more proof is needed."
        )
        session = getattr(map, 'session', None) or getattr(self, 'session', None)
        if not session or not getattr(session, 'event_manager', None):
            return
        session.event_manager.received_event({
            "event": 'console',
            "target": map,
            "source": entity,
            "message": message,
        })
        session.event_manager.received_event({
            "event": 'message',
            "source": entity,
            "target": self,
            "message": message,
        })
        deny_title = props.get('deny_title')
        if deny_title or props.get('deny_narration'):
            session.event_manager.received_event({
                'event': 'narration',
                'source': entity,
                'narration': {
                    'on_enter': {
                        'title': deny_title or 'Blocked',
                        'text': props.get('deny_narration') or message,
                        'once': False,
                    }
                },
                'map_name': getattr(map, 'name', None),
            })

    def on_enter(self, entity: Entity, map, battle=None):
        if not self._session_gate_allows(entity, map):
            self._deny_entry(entity, map)
            return

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
        return self.properties.get('label') or self.properties.get('name') or 'ground'

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
