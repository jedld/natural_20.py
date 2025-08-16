from typing import Iterable, Iterator, MutableMapping, MutableSequence, Tuple, Any, Dict, List, Optional


class CopyOnWriteDict(MutableMapping):
    def __init__(self, shared_ref: Optional[Dict[Any, Any]] = None) -> None:
        self._data: Dict[Any, Any] = shared_ref if shared_ref is not None else {}
        self._shared: bool = True

    # internal
    def _detach(self) -> None:
        if self._shared:
            self._data = dict(self._data)
            self._shared = False

    # Mapping protocol
    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._detach()
        self._data[key] = value

    def __delitem__(self, key: Any) -> None:
        self._detach()
        del self._data[key]

    def __iter__(self) -> Iterator:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    # Common mutating helpers
    def clear(self) -> None:  # type: ignore[override]
        self._detach()
        self._data.clear()

    def pop(self, key: Any, default: Any = None) -> Any:  # type: ignore[override]
        self._detach()
        return self._data.pop(key, default)

    def popitem(self) -> Tuple[Any, Any]:  # type: ignore[override]
        self._detach()
        return self._data.popitem()

    def setdefault(self, key: Any, default: Any = None) -> Any:  # type: ignore[override]
        self._detach()
        return self._data.setdefault(key, default)

    def update(self, other=(), /, **kwds) -> None:  # type: ignore[override]
        self._detach()
        self._data.update(other, **kwds)

    # Introspection helpers
    @property
    def data(self) -> Dict[Any, Any]:
        return self._data


class CopyOnWriteList(MutableSequence):
    def __init__(self, shared_ref: Optional[List[Any]] = None) -> None:
        self._data: List[Any] = shared_ref if shared_ref is not None else []
        self._shared: bool = True

    # internal
    def _detach(self) -> None:
        if self._shared:
            self._data = list(self._data)
            self._shared = False

    # Sequence protocol
    def __getitem__(self, index: int) -> Any:
        return self._data[index]

    def __setitem__(self, index: int, value: Any) -> None:
        self._detach()
        self._data[index] = value

    def __delitem__(self, index: int) -> None:
        self._detach()
        del self._data[index]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator:
        return iter(self._data)

    def insert(self, index: int, value: Any) -> None:
        self._detach()
        self._data.insert(index, value)

    # Common mutating helpers
    def append(self, value: Any) -> None:  # type: ignore[override]
        self._detach()
        self._data.append(value)

    def extend(self, values: Iterable[Any]) -> None:  # type: ignore[override]
        self._detach()
        self._data.extend(values)

    def clear(self) -> None:  # type: ignore[override]
        self._detach()
        self._data.clear()

    def pop(self, index: int = -1) -> Any:  # type: ignore[override]
        self._detach()
        return self._data.pop(index)

    def remove(self, value: Any) -> None:  # type: ignore[override]
        self._detach()
        self._data.remove(value)

    def reverse(self) -> None:  # type: ignore[override]
        self._detach()
        self._data.reverse()

    def sort(self, *args, **kwargs) -> None:  # type: ignore[override]
        self._detach()
        self._data.sort(*args, **kwargs)

    # Introspection helpers
    @property
    def data(self) -> List[Any]:
        return self._data
