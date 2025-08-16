from __future__ import annotations

import uuid
import weakref
from typing import Any, Optional


class EntityRegistry:
    """
    Centralized UID ⇄ Entity registry to support serialization-friendly references.

    - Keys are str(entity_uid) to normalize mixed UUID/str usages across the codebase.
    - Values are weak references so unused entities don’t leak.
    - Safe to register the same entity multiple times.
    """

    def __init__(self) -> None:
        self._uid_to_entity = weakref.WeakValueDictionary()
        self._entity_to_uid = weakref.WeakKeyDictionary()
        # Fallback containers for objects that cannot be weak-referenced
        self._uid_to_entity_strong = {}
        self._entity_to_uid_strong = {}

    @staticmethod
    def _normalize_uid(uid: Any) -> str:
        if isinstance(uid, uuid.UUID):
            return str(uid)
        return str(uid)

    def register(self, entity: Any) -> str:
        """Register an entity and return its normalized UID string."""
        if entity is None:
            return ""

        # Read without mutating type to avoid breaking code paths that expect UUID vs str
        uid = getattr(entity, "entity_uid", None)
        if uid is None:
            # Fallback: assign a new UUID but keep it as str for portability
            uid_str = str(uuid.uuid4())
            try:
                setattr(entity, "entity_uid", uid_str)
            except Exception:
                # If entity is not writable, still track it internally
                pass
        else:
            uid_str = self._normalize_uid(uid)

        # Try weak mapping first; fall back to strong mapping when necessary
        try:
            self._uid_to_entity[uid_str] = entity
        except TypeError:
            # Not weakref-able
            self._uid_to_entity_strong[uid_str] = entity

        try:
            self._entity_to_uid[entity] = uid_str
        except TypeError:
            # Not weakref-able key
            self._entity_to_uid_strong[id(entity)] = uid_str
        except Exception:
            pass
        return uid_str

    def unregister(self, entity: Any) -> None:
        if entity is None:
            return
        uid_str = None
        try:
            uid_str = self._entity_to_uid.pop(entity, None)
        except Exception:
            uid_str = None
        # Also check strong reverse map
        strong_uid = self._entity_to_uid_strong.pop(id(entity), None)
        if strong_uid and not uid_str:
            uid_str = strong_uid
        if uid_str:
            try:
                self._uid_to_entity.pop(uid_str, None)
            except Exception:
                pass
            # Clean strong map if present
            self._uid_to_entity_strong.pop(uid_str, None)

    def get(self, uid: Any) -> Optional[Any]:
        if uid is None:
            return None
        uid_norm = self._normalize_uid(uid)
        ent = self._uid_to_entity.get(uid_norm)
        if ent is not None:
            return ent
        return self._uid_to_entity_strong.get(uid_norm)

    def get_uid(self, entity: Any) -> Optional[str]:
        if entity is None:
            return None
        # Prefer cached mapping; fallback to attribute normalization
        try:
            uid_str = self._entity_to_uid.get(entity)
        except TypeError:
            # Not weakref-able
            uid_str = None
        if uid_str:
            return uid_str
        strong = self._entity_to_uid_strong.get(id(entity))
        if strong:
            return strong
        uid = getattr(entity, "entity_uid", None)
        if uid is None:
            return None
        return self._normalize_uid(uid)

    def clear(self) -> None:
        self._uid_to_entity.clear()
        self._entity_to_uid.clear()
        self._uid_to_entity_strong.clear()
        self._entity_to_uid_strong.clear()

    def pin(self, entity: Any) -> Optional[str]:
        """Keep a strong reference to an entity in the registry.

        Returns the entity's UID string. Safe to call multiple times.
        """
        if entity is None:
            return None
        uid_str = self.register(entity)
        if uid_str:
            try:
                self._uid_to_entity_strong[uid_str] = entity
                self._entity_to_uid_strong[id(entity)] = uid_str
            except Exception:
                pass
        return uid_str
