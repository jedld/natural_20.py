"""Phase 4 ResourcePool framework.

A small, additive helper that lets entities track limited-use resources
(Bardic Inspiration, Channel Divinity, Ki, Action Surge, Wild Shape,
Rage, Lay-on-Hands HP pool, etc.) with uniform consumption and rest
restoration semantics. Existing per-attribute counters
(``second_wind_count``, ``wild_shape_count`` …) keep working — opt-in.

Example::

    entity.register_resource('inspiration', max_value=4, restore_on='long_rest')
    if entity.consume_resource('inspiration'):
        ...

``restore_on`` accepts ``'short_rest'``, ``'long_rest'``, ``'turn'`` (resets
on ``start_of_turn``), or ``'never'``.
"""

from __future__ import annotations


_VALID_RESTORE = {'short_rest', 'long_rest', 'turn', 'never'}


class ResourcePool:
    """A capped counter that refills on a configurable rest event."""

    def __init__(self, name: str, max_value: int, *, restore_on: str = 'long_rest',
                 current: int = None):
        if restore_on not in _VALID_RESTORE:
            raise ValueError(f"restore_on must be one of {_VALID_RESTORE}, got {restore_on!r}")
        self.name = str(name)
        self.max_value = int(max_value)
        self.restore_on = restore_on
        self.current = int(self.max_value if current is None else current)

    # ------------------------------------------------------------------
    def available(self, n: int = 1) -> bool:
        return self.current >= int(n)

    def consume(self, n: int = 1) -> bool:
        n = int(n)
        if self.current < n:
            return False
        self.current -= n
        return True

    def restore(self, n: int = None) -> int:
        """Restore ``n`` (default: full) charges, capped at ``max_value``."""
        if n is None:
            self.current = self.max_value
        else:
            self.current = min(self.max_value, self.current + int(n))
        return self.current

    def restore_for(self, rest_kind: str) -> bool:
        """Refill if this pool's ``restore_on`` matches ``rest_kind``."""
        if self.restore_on == rest_kind:
            self.restore()
            return True
        return False

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'max_value': self.max_value,
            'restore_on': self.restore_on,
            'current': self.current,
        }

    @staticmethod
    def from_dict(data: dict) -> 'ResourcePool':
        return ResourcePool(
            data['name'],
            int(data.get('max_value', 0)),
            restore_on=data.get('restore_on', 'long_rest'),
            current=int(data.get('current', data.get('max_value', 0))),
        )

    def __repr__(self):
        return f"ResourcePool(name={self.name!r}, current={self.current}/{self.max_value}, restore_on={self.restore_on!r})"
