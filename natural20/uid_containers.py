from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Iterator, Optional


def _uid_for(session, obj: Any) -> Optional[str]:
    if obj is None:
        return None
    uid = getattr(obj, 'entity_uid', None)
    if uid is None:
        uid = session.uid_for(obj)
    return str(uid) if uid is not None else None


class EntitiesUIDMap(MutableMapping):
    """
    Dict-like mapping that stores keys by UID (str) internally but exposes
    a mapping keyed by live objects resolved via the session registry.

    Values are stored as-is (typically positions or metadata dicts).
    """

    def __init__(self, session, initial: Optional[dict[Any, Any]] = None):
        self._session = session
        self._uid_to_value: dict[str, Any] = {}
        if initial:
            for k, v in initial.items():
                uid = _uid_for(session, k) if not isinstance(k, str) else k
                if uid is not None:
                    # Seed registry with live object keys on construction
                    if not isinstance(k, str):
                        try:
                            self._session.register_entity(k)
                        except Exception:
                            pass
                    self._uid_to_value[str(uid)] = v

    def __getitem__(self, key: Any) -> Any:
        uid = _uid_for(self._session, key) if not isinstance(key, str) else key
        if uid is None:
            raise KeyError(key)
        return self._uid_to_value[uid]

    def __setitem__(self, key: Any, value: Any) -> None:
        uid = _uid_for(self._session, key) if not isinstance(key, str) else key
        if uid is None:
            raise KeyError(key)
        if not isinstance(key, str):
            self._session.register_entity(key)
        self._uid_to_value[str(uid)] = value

    def __delitem__(self, key: Any) -> None:
        uid = _uid_for(self._session, key) if not isinstance(key, str) else key
        if uid is None:
            raise KeyError(key)
        del self._uid_to_value[str(uid)]

    def __iter__(self) -> Iterator[Any]:
        for uid in list(self._uid_to_value.keys()):
            ent = self._session.entity_registry.get(uid)
            if ent is not None:
                yield ent

    def __len__(self) -> int:
        return len(self._uid_to_value)

    def get_by_uid(self, uid: str, default=None):
        return self._uid_to_value.get(str(uid), default)

    def set_by_uid(self, uid: str, value: Any) -> None:
        self._uid_to_value[str(uid)] = value

    def del_by_uid(self, uid: str) -> None:
        self._uid_to_value.pop(str(uid), None)

    def items_uid(self):
        return self._uid_to_value.items()

    def as_uid_dict(self) -> dict[str, Any]:
        return dict(self._uid_to_value)


class ObjectsCellProxy:
    def __init__(self, session, uid_list: list[str]):
        self._session = session
        self._uids = uid_list

    def __iter__(self):
        for uid in list(self._uids):
            obj = self._session.entity_registry.get(uid)
            if obj is not None:
                yield obj

    def __len__(self):
        return len(self._uids)

    def __getitem__(self, idx):
        uid = self._uids[idx]
        return self._session.entity_registry.get(uid)

    def append(self, obj):
        uid = obj if isinstance(obj, str) else _uid_for(self._session, obj)
        if uid is None:
            return
        if not isinstance(obj, str):
            self._session.register_entity(obj)
        self._uids.append(str(uid))

    def remove(self, obj):
        uid = obj if isinstance(obj, str) else _uid_for(self._session, obj)
        if uid is None:
            return
        self._uids.remove(str(uid))

    def clear(self):
        self._uids.clear()


class ObjectsGrid:
    def __init__(self, session, width: int, height: int):
        self._session = session
        self._w = width
        self._h = height
        self._grid: list[list[list[str]]] = [
            [[] for _ in range(height)] for _ in range(width)
        ]

    class _Col:
        def __init__(self, parent: 'ObjectsGrid', x: int):
            self._parent = parent
            self._x = x

        def __getitem__(self, y: int) -> ObjectsCellProxy:
            if y < 0 or y >= self._parent._h:
                raise IndexError(y)
            return ObjectsCellProxy(self._parent._session, self._parent._grid[self._x][y])

    def __getitem__(self, x: int) -> 'ObjectsGrid._Col':
        if x < 0 or x >= self._w:
            raise IndexError(x)
        return ObjectsGrid._Col(self, x)

    def cell_uids(self, x: int, y: int) -> list[str]:
        return self._grid[x][y]

    def __contains__(self, obj: Any) -> bool:
        uid = obj if isinstance(obj, str) else _uid_for(self._session, obj)
        if uid is None:
            return False
        uid = str(uid)
        # Scan grid for presence of UID
        for x in range(self._w):
            col = self._grid[x]
            for y in range(self._h):
                if uid in col[y]:
                    return True
        return False


class TokensCellProxy:
    def __init__(self, session, cell: Optional[dict]):
        self._session = session
        self._cell = cell

    def __bool__(self):
        return bool(self._cell)

    def __len__(self):
        return len(self._cell) if self._cell else 0

    def __getitem__(self, key):
        if not self._cell:
            raise KeyError(key)
        if key == 'entity':
            uid = self._cell.get('entity_uid')
            return self._session.entity_registry.get(uid)
        return self._cell.get(key)

    def as_dict(self):
        return dict(self._cell) if self._cell else None


class TokensGrid:
    def __init__(self, session, width: int, height: int):
        self._session = session
        self._w = width
        self._h = height
        self._grid: list[list[Optional[dict]]] = [
            [None for _ in range(height)] for _ in range(width)
        ]

    class _Col:
        def __init__(self, parent: 'TokensGrid', x: int):
            self._parent = parent
            self._x = x

        def __getitem__(self, y: int):
            if y < 0 or y >= self._parent._h:
                raise IndexError(y)
            return TokensCellProxy(self._parent._session, self._parent._grid[self._x][y])

        def __setitem__(self, y: int, value):
            if value is None:
                self._parent._grid[self._x][y] = None
                return
            if isinstance(value, TokensCellProxy):
                self._parent._grid[self._x][y] = dict(value._cell) if value._cell else None
                return
            if isinstance(value, dict):
                ent = value.get('entity')
                uid = value.get('entity_uid')
                token = value.get('token')
                if ent is not None and uid is None:
                    uid = _uid_for(self._parent._session, ent)
                    self._parent._session.register_entity(ent)
                self._parent._grid[self._x][y] = {'entity_uid': str(uid) if uid is not None else None, 'token': token}
                return
            self._parent._grid[self._x][y] = None

    def __getitem__(self, x: int):
        if x < 0 or x >= self._w:
            raise IndexError(x)
        return TokensGrid._Col(self, x)

    def cell(self, x: int, y: int):
        return self._grid[x][y]

    def __contains__(self, obj: Any) -> bool:
        uid = obj if isinstance(obj, str) else _uid_for(self._session, obj)
        if uid is None:
            return False
        uid = str(uid)
        for x in range(self._w):
            for y in range(self._h):
                cell = self._grid[x][y]
                if cell and cell.get('entity_uid') == uid:
                    return True
        return False
