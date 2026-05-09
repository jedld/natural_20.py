"""Shared context object passed to every MCP tool invocation.

The context gives tools lazy access to webapp-level singletons (the
running ``GameManagement`` instance, the loaded ``Session``, the
``socketio`` emitter, the ``output_logger`` and the
``action_type_to_class`` dispatcher) without forcing the tool modules
to import :mod:`webapp.app` directly. That avoids circular imports when
``app.py`` itself wires up the MCP blueprint at startup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class MCPContext:
    """Lazy bag of references the MCP tools need to operate.

    All fields are *callables* returning the current object, so the
    blueprint stays valid even if ``current_game`` is rebound (for
    example after a campaign reload).
    """

    game_session_getter: Callable[[], Any]
    current_game_getter: Callable[[], Any]
    socketio_getter: Callable[[], Any] = field(default=lambda: None)
    output_logger_getter: Callable[[], Any] = field(default=lambda: None)
    action_class_resolver: Optional[Callable[[str], Any]] = None
    extra: dict = field(default_factory=dict)

    @property
    def game_session(self):
        return self.game_session_getter()

    @property
    def current_game(self):
        return self.current_game_getter()

    @property
    def socketio(self):
        return self.socketio_getter()

    @property
    def output_logger(self):
        return self.output_logger_getter()

    # ---- helpers ----
    def resolve_entity(self, entity_id: str):
        """Locate an entity (or interactable object) by uid across maps."""
        cg = self.current_game
        if cg is None:
            return None
        getter = getattr(cg, 'get_entity_by_uid', None)
        entity = getter(entity_id) if getter else None
        if entity is not None:
            return entity
        for battle_map in (getattr(cg, 'maps', {}) or {}).values():
            try:
                ent = battle_map.entity_by_uid(entity_id) or battle_map.object_by_uid(entity_id)
            except Exception:
                ent = None
            if ent is not None:
                return ent
        return None

    def resolve_map(self, map_name: Optional[str]):
        cg = self.current_game
        maps = getattr(cg, 'maps', {}) if cg else {}
        if not map_name:
            return maps.get('index') or (next(iter(maps.values()), None) if maps else None)
        return maps.get(map_name)

    def map_for_entity(self, entity):
        cg = self.current_game
        if cg is None or entity is None:
            return None
        getter = getattr(cg, 'get_map_for_entity', None)
        return getter(entity) if getter else None

    def emit_refresh(self):
        socketio = self.socketio
        if socketio is None:
            return
        try:
            socketio.emit('message', {'type': 'refresh_map'})
        except Exception:
            pass

    def log_dm(self, message: str):
        logger = self.output_logger
        if logger is None:
            return
        try:
            logger.log(message, visibility='dm_only')
        except Exception:
            pass

    def resolve_action_class(self, action_type: str):
        if self.action_class_resolver is None:
            raise RuntimeError('No action_class_resolver configured on MCPContext')
        return self.action_class_resolver(action_type)
