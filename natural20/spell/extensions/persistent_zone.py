"""Persistent area-of-effect zone primitive.

A ``PersistentAoEZone`` represents a region of squares that lingers across
turns and reacts to creatures entering or starting their turn inside it
(Spike Growth, Web, Cloud of Daggers, Hunger of Hadar, Spirit Guardians,
etc.). Concrete spells subclass it and override ``on_enter`` /
``on_turn_start`` / ``on_dismiss`` as needed.

Zones register themselves with ``Battle.active_zones`` via
``Battle.register_zone(zone)``. The battle ticks them on
``start_of_turn`` / ``end_of_turn`` and on ``movement_step`` events; zones
self-expire by ``expiration_round`` or ``expiration_time``, on owner death
or unconsciousness, or on concentration drop.
"""

from __future__ import annotations

import uuid
from typing import Iterable, List, Optional, Tuple


class PersistentAoEZone:
    """Base class for a persistent square-occupying spell effect."""

    __slots__ = (
        "id", "owner", "battle", "map", "shape", "squares",
        "expiration_round", "expiration_time", "concentration",
        "name", "spell", "_dismissed",
    )

    def __init__(
        self,
        owner,
        battle,
        map,
        squares: Iterable[Tuple[int, int]],
        *,
        name: str = "zone",
        shape: str = "radius",
        duration_rounds: Optional[int] = None,
        concentration: bool = False,
        spell=None,
    ):
        self.id = f"zone_{uuid.uuid4().hex[:10]}"
        self.owner = owner
        self.battle = battle
        self.map = map
        self.shape = shape
        self.squares: List[Tuple[int, int]] = [tuple(s) for s in squares]
        self.name = name
        self.spell = spell
        self.concentration = concentration
        self._dismissed = False
        self.expiration_round = None
        self.expiration_time = None
        if duration_rounds is not None and battle is not None:
            self.expiration_round = battle.current_round() + int(duration_rounds)
        if duration_rounds is not None and getattr(getattr(owner, 'session', None), 'game_time', None) is not None:
            # 1 round = 6 seconds; track wall-clock too for save/load resilience.
            self.expiration_time = owner.session.game_time + int(duration_rounds) * 6

    # --- lifecycle hooks (override in subclasses) ----------------------

    def on_enter(self, entity):  # pragma: no cover - override
        return None

    def on_turn_start(self, entity):  # pragma: no cover - override
        return None

    def on_turn_end(self, entity):  # pragma: no cover - override
        return None

    def on_dismiss(self):  # pragma: no cover - override
        return None

    # --- queries -------------------------------------------------------

    def contains(self, pos: Tuple[int, int]) -> bool:
        return tuple(pos) in self.squares

    def occupants(self):
        if self.map is None:
            return []
        seen = []
        for x, y in self.squares:
            ent = self.map.entity_at(x, y)
            if ent is not None and ent not in seen:
                seen.append(ent)
        return seen

    # --- ticking -------------------------------------------------------

    def expired(self) -> bool:
        if self._dismissed:
            return True
        if self.owner is not None:
            if hasattr(self.owner, 'dead') and self.owner.dead():
                return True
            if hasattr(self.owner, 'conscious') and not self.owner.conscious():
                # 5e: concentration drops on incapacitation (incl. unconscious).
                if self.concentration:
                    return True
        if self.expiration_round is not None and self.battle is not None:
            if self.battle.current_round() > self.expiration_round:
                return True
        if self.expiration_time is not None and self.owner is not None:
            session = getattr(self.owner, 'session', None)
            if session is not None and getattr(session, 'game_time', 0) > self.expiration_time:
                return True
        return False

    def dismiss(self):
        if self._dismissed:
            return
        self._dismissed = True
        try:
            self.on_dismiss()
        finally:
            if self.battle is not None:
                self.battle.unregister_zone(self)

    # --- serialization (Phase 4 will plug into the registry) -----------

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'shape': self.shape,
            'squares': [list(s) for s in self.squares],
            'owner_uid': getattr(self.owner, 'entity_uid', None),
            'expiration_round': self.expiration_round,
            'expiration_time': self.expiration_time,
            'concentration': self.concentration,
        }
