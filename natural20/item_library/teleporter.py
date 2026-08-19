from natural20.item_library.object import Object
from typing import Optional
from natural20.entity import Entity

_PARTY_TRAVEL_STATE = '_party_travel'


def is_party_travel_properties(props: Optional[dict]) -> bool:
    """True when YAML/object properties describe a party map-set teleporter."""
    if not isinstance(props, dict):
        return False
    if props.get('party_travel') or props.get('party'):
        return True
    type_name = str(props.get('type') or props.get('object_type') or '').strip().lower()
    return type_name in {'party_teleporter', 'party_travel'}


def is_party_travel_object(obj) -> bool:
    if obj is None:
        return False
    if callable(getattr(obj, 'is_party_travel', None)):
        try:
            return bool(obj.is_party_travel())
        except Exception:
            pass
    return is_party_travel_properties(getattr(obj, 'properties', None))


def _party_travel_state(session) -> dict:
    if session is None:
        return {}
    state = getattr(session, 'session_state', None)
    if not isinstance(state, dict):
        session.session_state = {}
        state = session.session_state
    bucket = state.get(_PARTY_TRAVEL_STATE)
    if not isinstance(bucket, dict):
        bucket = {'pending': {}, 'declined': {}}
        state[_PARTY_TRAVEL_STATE] = bucket
    bucket.setdefault('pending', {})
    bucket.setdefault('declined', {})
    return bucket


def _entity_uid(entity) -> str:
    return str(getattr(entity, 'entity_uid', '') or '')


def party_travel_after_step(entity, battle_map, pos_x, pos_y) -> None:
    """Clear a declined party-travel pad once the entity steps off it."""
    session = getattr(battle_map, 'session', None)
    uid = _entity_uid(entity)
    if not uid or session is None:
        return
    bucket = _party_travel_state(session)
    declined = bucket.setdefault('declined', {})
    if uid not in declined:
        return
    still_on_pad = False
    try:
        for obj in battle_map.objects_at(pos_x, pos_y):
            if is_party_travel_object(obj) and str(getattr(obj, 'target_map', '') or '') == declined.get(uid):
                still_on_pad = True
                break
    except Exception:
        still_on_pad = False
    if not still_on_pad:
        declined.pop(uid, None)


def resolve_party_travel_prompt(session, entity, *, declined: bool = False, target_map: Optional[str] = None) -> None:
    """Clear pending prompt state after the player answers."""
    uid = _entity_uid(entity)
    if not uid or session is None:
        return
    bucket = _party_travel_state(session)
    pending = bucket.setdefault('pending', {})
    remembered = pending.pop(uid, None)
    dest = target_map or remembered
    if declined and dest:
        bucket.setdefault('declined', {})[uid] = dest
    else:
        bucket.setdefault('declined', {}).pop(uid, None)


class Teleporter(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.target_map = properties.get('target_map', None)
        self.target_position = properties.get('target_position', [0, 0])

    def is_party_travel(self) -> bool:
        return is_party_travel_properties(getattr(self, 'properties', None))

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

    def _is_player_character(self, entity: Entity) -> bool:
        try:
            from natural20.player_character import PlayerCharacter
            return isinstance(entity, PlayerCharacter)
        except Exception:
            return False

    def _entity_on_pad(self, entity: Entity) -> bool:
        battle_map = getattr(self, 'map', None)
        if battle_map is None or entity is None:
            return False
        try:
            return tuple(battle_map.position_of(entity)) == tuple(battle_map.position_of(self))
        except (ValueError, KeyError, TypeError, AttributeError):
            return False

    def _destination_display_name(self, session) -> str:
        if not self.target_map:
            return 'another map'
        dest_map = session.maps.get(self.target_map) if session else None
        if dest_map is not None:
            name = getattr(dest_map, 'name', None)
            if name:
                return str(name)
        return str(self.target_map).replace('_', ' ').title()

    def party_travel_prompt_text(self, session) -> str:
        props = getattr(self, 'properties', {}) or {}
        custom = (props.get('prompt') or props.get('prompt_message') or '').strip()
        if custom:
            return custom
        dest = self._destination_display_name(session)
        return (
            f"The entire party will be transported to {dest}. "
            "Player characters and their sidekicks who are not already there "
            "will appear at that map's spawn points. Continue?"
        )

    def party_travel_prompt_title(self, session) -> str:
        props = getattr(self, 'properties', {}) or {}
        custom = (props.get('prompt_title') or '').strip()
        if custom:
            return custom
        dest = self._destination_display_name(session)
        return f"Travel to {dest}?"

    def party_travel_interact_label(self, session=None) -> str:
        """Action-bar / mouseover label for retrying party travel from the pad."""
        dest = self._destination_display_name(session or getattr(self, 'session', None))
        return f"Travel with party → {dest}"

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = super().available_interactions(entity, battle, admin=admin) or {}
        if not self.is_party_travel():
            return interactions
        if not admin and not self._is_player_character(entity):
            return interactions
        if not admin and not self._entity_on_pad(entity):
            return interactions

        label = self.party_travel_interact_label(getattr(self, 'session', None))
        interactions['party_travel'] = {
            'prompt': label,
            'label': label,
        }
        if not self._session_gate_allows(entity, getattr(self, 'map', None)):
            props = getattr(self, 'properties', {}) or {}
            interactions['party_travel']['disabled'] = True
            interactions['party_travel']['disabled_text'] = (
                props.get('deny_message') or 'object.teleporter.not_ready'
            )
        elif battle is not None and getattr(battle, 'started', False):
            interactions['party_travel']['disabled'] = True
            interactions['party_travel']['disabled_text'] = (
                'Cannot travel with the party while a battle is in progress.'
            )
        return interactions

    def resolve(self, entity, action, other_params, opts=None):
        if action == 'party_travel':
            return {'action': action}
        return super().resolve(entity, action, other_params, opts)

    def use(self, entity, result, session=None):
        if result.get('action') == 'party_travel':
            battle_map = result.get('map') or getattr(self, 'map', None)
            self._handle_party_travel(
                entity, battle_map, result.get('battle'), force=True,
            )
            return True
        return super().use(entity, result, session)

    def _handle_party_travel(self, entity: Entity, map, battle=None, *, force: bool = False) -> None:
        if not self._is_player_character(entity):
            return
        if not self._session_gate_allows(entity, map):
            self._deny_entry(entity, map)
            return
        if battle is not None and getattr(battle, 'started', False):
            props = getattr(self, 'properties', {}) or {}
            message = props.get('deny_message') or (
                f"{entity.name} cannot use {self.label()} while a battle is in progress."
            )
            session = getattr(map, 'session', None) or getattr(self, 'session', None)
            if session and getattr(session, 'event_manager', None):
                session.event_manager.received_event({
                    "event": 'console', "target": map, "source": entity, "message": message,
                })
            return

        session = getattr(map, 'session', None) or getattr(self, 'session', None)
        if not self.target_map or session is None:
            return
        if self.target_map not in (getattr(session, 'maps', {}) or {}):
            if getattr(session, 'event_manager', None):
                session.event_manager.received_event({
                    "event": 'console', "target": map, "source": entity,
                    "message": (
                        f"{entity.name} stepped on {self.label()} but "
                        f"target_map '{self.target_map}' is not registered."
                    ),
                })
            return

        uid = _entity_uid(entity)
        bucket = _party_travel_state(session)
        pending = bucket.setdefault('pending', {})
        declined = bucket.setdefault('declined', {})
        if force:
            declined.pop(uid, None)
        if pending.get(uid) == self.target_map:
            return
        if not force and declined.get(uid) == self.target_map:
            return

        if not getattr(session, 'event_manager', None):
            return
        pending[uid] = self.target_map
        session.event_manager.received_event({
            "event": 'party_travel_prompt',
            "source": entity,
            "target": self,
            "map": map,
            "map_name": getattr(map, 'name', None),
            "target_map": self.target_map,
            "target_map_set": session.map_set_for(self.target_map) if hasattr(session, 'map_set_for') else None,
            "title": self.party_travel_prompt_title(session),
            "message": self.party_travel_prompt_text(session),
        })

    def on_enter(self, entity: Entity, map, battle=None):
        if self.is_party_travel():
            self._handle_party_travel(entity, map, battle)
            return

        if not self._session_gate_allows(entity, map):
            self._deny_entry(entity, map)
            return

        entity_placed = False
        session = getattr(map, 'session', None) or getattr(self, 'session', None)
        if self.target_map and session is not None and not session.same_map_set(getattr(map, 'name', None), self.target_map):
            if getattr(session, 'event_manager', None):
                session.event_manager.received_event({
                    "event": 'console', "target": map, "source": entity,
                    "message": (
                        f"{entity.name} cannot use {self.label()} — "
                        f"target_map '{self.target_map}' is in another map set"
                    ),
                })
            self._deny_entry(entity, map)
            return

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
        (alias: ``marker``). Party-travel pads default to visible.
        """
        props = getattr(self, 'properties', {}) or {}
        if 'visible' in props or 'marker' in props:
            return bool(props.get('visible') or props.get('marker'))
        return self.is_party_travel()

    def marker_color(self):
        """CSS color used for the visible-teleporter border. Configurable via
        the YAML key ``marker_color``; defaults to green.
        """
        props = getattr(self, 'properties', {}) or {}
        return props.get('marker_color') or '#22c55e'

    def destination_label(self):
        """Human-readable destination for map UI hover labels."""
        props = getattr(self, 'properties', {}) or {}
        session = getattr(self, 'session', None)
        if session is None:
            session = getattr(getattr(self, 'map', None), 'session', None)

        if self.target_map:
            dest_map = session.maps.get(self.target_map) if session else None
            if dest_map and getattr(dest_map, 'name', None):
                base = str(dest_map.name)
            else:
                base = str(self.target_map).replace('_', ' ').title()
        else:
            target_position = self.target_position or [0, 0]
            base = f"Square ({target_position[0]}, {target_position[1]})"

        custom = (props.get('label') or '').strip()
        if custom and custom.casefold() != base.casefold():
            return f"{custom} → {base}"
        return base

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
