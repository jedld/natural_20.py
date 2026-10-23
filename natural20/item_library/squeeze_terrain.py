"""Generic squeeze-only terrain.

A tile that creatures larger than ``max_pass_size`` cannot enter at all, while
creatures of that size or smaller pass by squeezing (the standard +10 ft
movement cost applied by the engine's squeeze rules). This models collapsed
rubble, narrow fissures, and similar gaps that a Small or Medium creature can
squeeze through but a Large one cannot.

YAML (object definition in items/objects.yml or a campaign override)::

    rubble_passage:
      name: Rubble Passage
      item_class: SqueezeTerrain
      max_pass_size: medium     # tiny | small | medium | large | huge
      passable: false           # base passability; passable_for() decides
      placeable: false
      opaque: false
      movement_cost: 2
      token:
        - '#'

``max_pass_size`` defaults to ``medium`` when omitted.
"""
from __future__ import annotations

from typing import Optional

from natural20.item_library.object import Object
from natural20.utils.item_size import size_rank


class SqueezeTerrain(Object):
    """Terrain passable only by creatures of ``max_pass_size`` or smaller."""

    def __init__(self, session, map, properties=None):
        props = properties or {}
        super().__init__(session, map, props)
        self.max_pass_size = props.get('max_pass_size', 'medium')

    def passable(self, origin=None) -> bool:
        # The base check is "blocked"; per-creature decisions go through
        # passable_for(), which the map consults when it exists.
        return self.properties.get('passable', False)

    def passable_for(self, entity, origin_pos=None) -> bool:
        """Return True when ``entity`` is small enough to squeeze through."""
        if entity is None:
            return self.passable(origin_pos)
        try:
            entity_rank = entity.size_identifier()
        except Exception:
            return self.passable(origin_pos)
        cap = size_rank(self.max_pass_size, default='medium')
        return entity_rank <= cap

    def opaque(self, origin=None) -> bool:
        # Rubble does not block sight beyond its own footprint.
        return bool(self.properties.get('opaque', False)) and not self.dead()

    def token(self) -> Optional[str]:
        return self.properties.get('token')
