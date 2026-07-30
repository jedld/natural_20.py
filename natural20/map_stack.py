"""Multi-level map stacks: shared world coordinates across stacked floor maps."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from natural20.map_annotations import list_map_annotations, annotation_contains_point


@dataclass(frozen=True)
class WorldCoord:
    x: int
    y: int
    elevation_ft: float = 0.0

    def as_tuple(self) -> tuple[int, int, float]:
        return (self.x, self.y, self.elevation_ft)


@dataclass
class FloorEntry:
    map_name: str
    map: Any
    anchor: tuple[int, int]
    elevation_ft: float
    role: str = 'overlay'
    edge_exit: str = 'descend'
    parapet_height_ft: float = 3.0
    ceiling_height_ft: Optional[float] = None

    @property
    def is_base(self) -> bool:
        return self.role == 'base'


@dataclass
class StackOpening:
    stack_id: str
    wx: int
    wy: int
    fall_damage: str = 'per_delta'


@dataclass
class FloorMask:
    stack_id: str
    floor: FloorEntry
    annotation: dict[str, Any]
    blocks_sight: str = 'up'


class MapStack:
  """Binds a base map and elevation overlays into one shared horizontal plane."""

  def __init__(self, stack_id: str, floors: list[FloorEntry], *, default_story_height_ft: float = 15.0):
    self.id = stack_id
    self.default_story_height_ft = default_story_height_ft
    self.floors = sorted(floors, key=lambda f: f.elevation_ft)
    self._by_map_name = {f.map_name: f for f in floors}
    self._openings: list[StackOpening] = []
    self._masks: list[FloorMask] = []
    self._window_cells: dict[tuple[int, int], set[str]] = {}
    self._index_annotations()

  def _index_annotations(self) -> None:
    for floor in self.floors:
      for raw in list_map_annotations(floor.map.properties):
        kind = str(raw.get('kind') or '').lower()
        stack_ref = raw.get('stack') or raw.get('stack_id')
        if stack_ref and stack_ref != self.id:
          continue
        if kind == 'stack_opening':
          for wx, wy in self._annotation_world_cells(floor, raw):
            self._openings.append(StackOpening(self.id, wx, wy, str(raw.get('fall_damage') or 'per_delta')))
        elif kind == 'floor_mask':
          self._masks.append(FloorMask(
            self.id,
            floor,
            raw,
            str(raw.get('blocks_sight') or 'up'),
          ))
      self._index_window_objects(floor)

  def _index_window_objects(self, floor: FloorEntry) -> None:
    for obj, pos in floor.map.interactable_objects.items():
      props = getattr(obj, 'properties', {}) or {}
      if props.get('type') == 'window' or props.get('peek_through') or props.get('fall_through'):
        wx, wy = self.local_to_world(floor.map_name, pos[0], pos[1])[:2]
        self._window_cells.setdefault((wx, wy), set()).add(floor.map_name)

  def _annotation_world_cells(self, floor: FloorEntry, raw: dict[str, Any]) -> list[tuple[int, int]]:
    kind = str(raw.get('kind') or 'point').lower()
    if kind in ('point', 'stack_opening'):
      pos = raw.get('pos') or raw.get('position')
      if pos and len(pos) >= 2:
        wx, wy = self.local_to_world(floor.map_name, int(pos[0]), int(pos[1]))[:2]
        cells = [(wx, wy)]
      else:
        cells = []
      bounds = raw.get('bounds') or {}
      if isinstance(bounds, dict) and bounds:
        try:
          for x in range(int(bounds['x1']), int(bounds['x2']) + 1):
            for y in range(int(bounds['y1']), int(bounds['y2']) + 1):
              wx, wy = self.local_to_world(floor.map_name, x, y)[:2]
              cells.append((wx, wy))
        except (KeyError, TypeError, ValueError):
          pass
      return cells
    if kind == 'area':
      bounds = raw.get('bounds') or {}
      cells = []
      for x in range(int(bounds.get('x1', 0)), int(bounds.get('x2', 0)) + 1):
        for y in range(int(bounds.get('y1', 0)), int(bounds.get('y2', 0)) + 1):
          wx, wy = self.local_to_world(floor.map_name, x, y)[:2]
          cells.append((wx, wy))
      return cells
    return []

  def floor_for_map(self, map_name: str) -> Optional[FloorEntry]:
    return self._by_map_name.get(map_name)

  def maps_in_stack(self) -> list[str]:
    return list(self._by_map_name.keys())

  def local_to_world(self, map_name: str, lx: int, ly: int) -> tuple[int, int, float]:
    floor = self._by_map_name[map_name]
    if floor.is_base:
      return (lx, ly, floor.elevation_ft)
    ax, ay = floor.anchor
    return (ax + lx, ay + ly, floor.elevation_ft)

  def world_to_local(self, wx: int, wy: int, map_name: str) -> Optional[tuple[int, int]]:
    floor = self._by_map_name.get(map_name)
    if floor is None:
      return None
    if floor.is_base:
      if 0 <= wx < floor.map.size[0] and 0 <= wy < floor.map.size[1]:
        return (wx, wy)
      return None
    ax, ay = floor.anchor
    lx, ly = wx - ax, wy - ay
    if 0 <= lx < floor.map.size[0] and 0 <= ly < floor.map.size[1]:
      return (lx, ly)
    return None

  def floors_at_world(self, wx: int, wy: int) -> list[FloorEntry]:
    hits = []
    for floor in self.floors:
      local = self.world_to_local(wx, wy, floor.map_name)
      if local is not None and self.has_slab_at(floor, local[0], local[1]):
        hits.append(floor)
    return hits

  def top_floor_at(self, wx: int, wy: int) -> Optional[FloorEntry]:
    hits = self.floors_at_world(wx, wy)
    return hits[-1] if hits else None

  def has_slab_at(self, floor: FloorEntry, lx: int, ly: int) -> bool:
    m = floor.map
    if lx < 0 or ly < 0 or lx >= m.size[0] or ly >= m.size[1]:
      return False
    if m.base_map[lx][ly] == '#':
      return False
    return True

  def in_overlay_footprint(self, floor: FloorEntry, wx: int, wy: int) -> bool:
    if floor.is_base:
      return True
    local = self.world_to_local(wx, wy, floor.map_name)
    return local is not None

  def is_building_exterior_shell(self, wx: int, wy: int) -> bool:
    """Base-map cell on the outside face of an overlay footprint (ground-floor shell)."""
    for floor in self.overlay_floors():
      if self.world_to_local(wx, wy, floor.map_name) is not None:
        return False
      ow, oh = floor.map.size
      ax, ay = floor.anchor
      for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        lx, ly = wx - ax + dx, wy - ay + dy
        if 0 <= lx < ow and 0 <= ly < oh and self.has_slab_at(floor, lx, ly):
          return True
    return False

  def is_stack_opening(self, wx: int, wy: int) -> bool:
    return any(o.wx == wx and o.wy == wy for o in self._openings)

  def stack_openings(self) -> list[StackOpening]:
    return list(self._openings)

  def transitions_from(self, map_name: str, lx: int, ly: int) -> list[tuple[str, int, int]]:
    """Return [(target_map_name, lx, ly), ...] for stack shaft / floor changes."""
    floor = self.floor_for_map(map_name)
    if floor is None:
      return []
    wx, wy, elev = self.local_to_world(map_name, lx, ly)
    results: list[tuple[str, int, int]] = []
    if self.is_stack_opening(wx, wy):
      lower = self.lower_floor_at(wx, wy, elev)
      if lower and lower.map_name != map_name:
        local = self.world_to_local(wx, wy, lower.map_name)
        if local:
          results.append((lower.map_name, local[0], local[1]))
      upper = self.upper_floor_at(wx, wy, elev)
      if upper and upper.map_name != map_name:
        local = self.world_to_local(wx, wy, upper.map_name)
        if local:
          results.append((upper.map_name, local[0], local[1]))
    return results

  def is_window_at(self, wx: int, wy: int, map_name: Optional[str] = None) -> bool:
    cells = self._window_cells.get((wx, wy))
    if not cells:
      return False
    if map_name is None:
      return True
    return map_name in cells

  def _mask_local_xy(self, mask: FloorMask, wx: int, wy: int) -> Optional[tuple[int, int]]:
    local = self.world_to_local(wx, wy, mask.floor.map_name)
    return local

  def floor_mask_blocks(self, wx: int, wy: int, direction: str) -> bool:
    direction = str(direction or '').lower()
    for mask in self._masks:
      blocks = str(mask.blocks_sight or 'up').lower()
      if blocks not in (direction, 'both'):
        continue
      local = self._mask_local_xy(mask, wx, wy)
      if local is None:
        continue
      if annotation_contains_point(mask.annotation, local[0], local[1]):
        return True
    return False

  def floor_mask_allows_sight(self, wx: int, wy: int, direction: str) -> bool:
    """Return True when a floor_mask punches a hole in the default opaque deck."""
    direction = str(direction or '').lower()
    for mask in self._masks:
      allows = mask.annotation.get('allows_sight')
      if not allows:
        continue
      if str(allows).lower() not in (direction, 'both'):
        continue
      local = self._mask_local_xy(mask, wx, wy)
      if local is None:
        continue
      if annotation_contains_point(mask.annotation, local[0], local[1]):
        return True
    return False

  def overlay_floors(self) -> list[FloorEntry]:
    return [f for f in self.floors if not f.is_base]

  def ceiling_elevation_ft(self, wx: int, wy: int, floor: FloorEntry) -> float:
    """Upper bound (z) of enclosed volume at this column on floor.

    Returns ``math.inf`` for open sky — columns with no upper overlay cover and no
    ``ceiling_height_ft`` on the current floor. When a higher overlay slab exists
    above this column, its deck elevation caps the volume below.
    """
    local = self.world_to_local(wx, wy, floor.map_name)
    if local is None:
      return math.inf
    if not self.has_slab_at(floor, local[0], local[1]):
      return math.inf
    upper = self.upper_floor_at(wx, wy, floor.elevation_ft)
    if upper is not None:
      return upper.elevation_ft
    if floor.ceiling_height_ft is not None:
      return floor.elevation_ft + floor.ceiling_height_ft
    return math.inf

  def is_open_sky(self, wx: int, wy: int, floor: FloorEntry) -> bool:
    return math.isinf(self.ceiling_elevation_ft(wx, wy, floor))

  def elevation_delta_ft(self, from_elevation: float, to_elevation: float) -> float:
    return max(0.0, from_elevation - to_elevation)

  def fall_damage_die(self, delta_ft: float) -> Optional[str]:
    if delta_ft <= 0:
      return None
    dice = min(20, max(0, int(delta_ft) // 10))
    if dice <= 0:
      return None
    return f'{dice}d6'

  def resolve_edge_exit(self, map_name: str, lx: int, ly: int) -> Optional[tuple[str, int, int]]:
    """When leaving overlay bounds, return (base_map_name, wx, wy) on base floor."""
    floor = self.floor_for_map(map_name)
    if floor is None or floor.is_base or floor.edge_exit != 'descend':
      return None
    wx, wy, _ = self.local_to_world(map_name, lx, ly)
    base = next((f for f in self.floors if f.is_base), None)
    if base is None:
      return None
    blx, bly = self.world_to_local(wx, wy, base.map_name)
    if blx is None:
      return None
    return (base.map_name, blx, bly)

  def lower_floor_at(self, wx: int, wy: int, elevation_ft: float) -> Optional[FloorEntry]:
    candidates = [f for f in self.floors_at_world(wx, wy) if f.elevation_ft < elevation_ft]
    return candidates[-1] if candidates else None

  def upper_floor_at(self, wx: int, wy: int, elevation_ft: float) -> Optional[FloorEntry]:
    candidates = [f for f in self.floors_at_world(wx, wy) if f.elevation_ft > elevation_ft]
    return candidates[0] if candidates else None


class MapStackRegistry:
  """Session-level registry of map stacks."""

  def __init__(self) -> None:
    self._stacks: dict[str, MapStack] = {}
    self._map_to_stack: dict[str, MapStack] = {}

  def register(self, stack: MapStack) -> None:
    self._stacks[stack.id] = stack
    for name in stack.maps_in_stack():
      self._map_to_stack[name] = stack

  def get(self, stack_id: str) -> Optional[MapStack]:
    return self._stacks.get(stack_id)

  def stack_for_map(self, map_name: str) -> Optional[MapStack]:
    return self._map_to_stack.get(map_name)

  def all_stacks(self) -> list[MapStack]:
    return list(self._stacks.values())

  @classmethod
  def from_game_config(cls, game_file: dict[str, Any], maps: dict[str, Any]) -> MapStackRegistry:
    registry = cls()
    stacks_cfg = game_file.get('map_stacks') or {}
    default_height = 15.0
    for stack_id, cfg in stacks_cfg.items():
      if not isinstance(cfg, dict):
        continue
      base_name = cfg.get('base')
      if not base_name or base_name not in maps:
        continue
      default_story_height_ft = float(cfg.get('default_story_height_ft', default_height))
      floors: list[FloorEntry] = []
      base_map = maps[base_name]
      base_floor_meta = (base_map.properties.get('floor') or {})
      base_ceiling = base_floor_meta.get('ceiling_height_ft')
      floors.append(FloorEntry(
        map_name=base_name,
        map=base_map,
        anchor=(0, 0),
        elevation_ft=float(base_floor_meta.get('elevation_ft', 0)),
        role='base',
        ceiling_height_ft=float(base_ceiling) if base_ceiling is not None else None,
      ))
      for floor_cfg in cfg.get('floors') or []:
        if not isinstance(floor_cfg, dict):
          continue
        map_name = floor_cfg.get('map')
        if not map_name or map_name not in maps:
          continue
        anchor = floor_cfg.get('anchor') or [0, 0]
        floor_meta = (maps[map_name].properties.get('floor') or {})
        ceiling_raw = floor_cfg.get('ceiling_height_ft', floor_meta.get('ceiling_height_ft'))
        floors.append(FloorEntry(
          map_name=map_name,
          map=maps[map_name],
          anchor=(int(anchor[0]), int(anchor[1])),
          elevation_ft=float(floor_cfg.get('elevation_ft', floor_meta.get('elevation_ft', default_story_height_ft))),
          role=str(floor_meta.get('role') or 'overlay'),
          edge_exit=str(floor_cfg.get('edge_exit') or floor_meta.get('edge_exit') or 'descend'),
          parapet_height_ft=float(floor_meta.get('parapet_height_ft', 3.0)),
          ceiling_height_ft=float(ceiling_raw) if ceiling_raw is not None else None,
        ))
      stack = MapStack(stack_id, floors, default_story_height_ft=default_story_height_ft)
      registry.register(stack)
      for floor in floors:
        floor.map.map_stack = stack
        floor.map.stack_floor = floor
    return registry
