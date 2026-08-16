import numpy as np

from natural20.item_library.common import Ground, StoneWall, StoneWallDirectional
from natural20.item_library.fireplace import Fireplace


# Terrain tiles are stored as interactable objects (one Ground/StoneWall per
# square). Scanning them on every light_at() call made map render O(tiles²).
_INERT_LIGHT_TYPES = (Ground, StoneWall, StoneWallDirectional)


class StaticLightBuilder:
    def __init__(self, battlemap):
        self.map = battlemap
        self.properties = battlemap.properties
        self.size = battlemap.size
        self.light_properties = self.properties.get('lights')
        self.light_map = self.properties.get('map', {}).get('light')
        self.base_illumination = self.properties.get('map', {}).get('illumination', 1.0)
        self.outdoor_ambient_illumination = self.base_illumination
        manual_light_map = self.properties.get('map', {}).get('light_map',[])
        self.outside_grid = self._build_outside_grid()
        self.lights = []
        self.fixed_lights = []
        self.invalidate_dynamic_cache()

        for _ in range(self.size[0]):
            row = []
            for _ in range(self.size[1]):
                row.append(0.0)
            self.fixed_lights.append(row)

        if manual_light_map:
            for cur_y, lines in enumerate(manual_light_map):
                for cur_x, c in enumerate(lines):
                    if not c=='.':
                        if c=='l':
                            self.fixed_lights[cur_x][cur_y] = 0.5
                        elif c=='h':
                            self.fixed_lights[cur_x][cur_y] = 1.0

        if self.light_map and self.light_properties:
            for cur_y, row in enumerate(self.light_map):
                for cur_x, key in enumerate(row):
                    if key in self.light_properties:
                        light = {
                            'position': [cur_x, cur_y]
                        }
                        light.update(self.light_properties[key])
                        self.lights.append(light)

    def invalidate_dynamic_cache(self):
        """Drop cached dynamic emitters so the next query rescans the map."""
        self._emitters = None
        self._darkness_sources = None
        self._gas_tiles = None
        self._tiny_huts = None

    def _build_outside_grid(self):
        map_block = self.properties.get('map', {}) or {}
        if bool(map_block.get('outdoor')):
            return [[True for _ in range(self.size[1])] for _ in range(self.size[0])]

        rows = map_block.get('outside') or []
        if not rows:
            return [[False for _ in range(self.size[1])] for _ in range(self.size[0])]

        grid = [[False for _ in range(self.size[1])] for _ in range(self.size[0])]
        for cur_y, line in enumerate(rows):
            for cur_x, ch in enumerate(line):
                if ch in ('o', 'O', 'x', 'X', '1'):
                    grid[cur_x][cur_y] = True
        return grid

    def is_outside(self, pos_x, pos_y):
        try:
            return bool(self.outside_grid[pos_x][pos_y])
        except Exception:
            return False

    def build_map(self):
        max_x, max_y = self.map.size

        light_map = np.full((max_x, max_y), self.base_illumination)
        for x in range(max_x):
            for index_2 in range(max_y):
                y = max_y - index_2 - 1
                tile_base = (
                    self.outdoor_ambient_illumination
                    if self.is_outside(x, y)
                    else self.base_illumination
                )
                intensity = tile_base
                for light in self.lights:
                    light_pos_x, light_pos_y = light['position']
                    bright_light = light.get('bright', 10) / self.map.feet_per_grid
                    dim_light = light.get('dim', 5) / self.map.feet_per_grid

                    in_bright, in_dim = self.map.light_in_sight(x, y, light_pos_x, light_pos_y, min_distance=bright_light,
                                                                distance=bright_light + dim_light,
                                                                inclusive=True)
                    intensity += 1.0 if in_bright else (0.5 if in_dim else 0.0)

                light_map[x][y] = intensity + self.fixed_lights[x][y]

        return light_map

    def _iter_dynamic_occupants(self):
        for source in (
            getattr(self.map, 'entities', None),
            getattr(self.map, 'interactable_objects', None),
        ):
            if not source:
                continue
            for entity in source:
                yield entity

    def _ensure_dynamic_sources(self):
        if self._emitters is not None:
            return

        emitters = []
        darkness_sources = []
        gas_tiles = set()
        tiny_huts = []
        TinyHutDome = None
        try:
            from natural20.spell.objects.tiny_hut import TinyHutDome as _TinyHutDome
            TinyHutDome = _TinyHutDome
        except Exception:
            TinyHutDome = None

        for entity in self._iter_dynamic_occupants():
            if isinstance(entity, _INERT_LIGHT_TYPES):
                continue
            if TinyHutDome is not None and isinstance(entity, TinyHutDome):
                tiny_huts.append(entity)

            light = None
            try:
                light = entity.light_properties()
            except Exception:
                light = None
            bright = 0.0
            dim = 0.0
            if light:
                bright = float(light.get('bright', 0.0) or 0.0)
                dim = float(light.get('dim', 0.0) or 0.0)
            # Fireplaces can be lit in place without a map mutation; keep them
            # live. Other emitters snapshot radii so equipped_items() is not
            # re-run on every tile during render.
            if isinstance(entity, Fireplace):
                emitters.append(('live', entity, None, None))
            elif (bright + dim) > 0.0:
                emitters.append(('snap', entity, bright, dim))

            dark_fn = getattr(entity, 'dark_properties', None)
            if callable(dark_fn):
                try:
                    dark = dark_fn()
                except Exception:
                    dark = None
                if dark and (dark.get('radius', 0) or 0) > 0:
                    darkness_sources.append(entity)

            props = getattr(entity, 'properties', None) or {}
            if props.get('stinking_cloud_gas') or props.get('obscuring_gas'):
                try:
                    ox, oy = self.map.entity_or_object_pos(entity)
                    gas_tiles.add((ox, oy))
                except Exception:
                    pass

        self._emitters = emitters
        self._darkness_sources = darkness_sources
        self._gas_tiles = gas_tiles
        self._tiny_huts = tiny_huts

    def light_at(self, pos_x, pos_y):
        self._ensure_dynamic_sources()

        intensity = 0.0
        feet_per_grid = self.map.feet_per_grid
        light_in_sight = self.map.light_in_sight
        entity_or_object_pos = self.map.entity_or_object_pos

        for kind, entity, snap_bright, snap_dim in self._emitters:
            if kind == 'live':
                light = entity.light_properties()
                if light is None:
                    continue
                bright_ft = float(light.get('bright', 0.0) or 0.0)
                dim_ft = float(light.get('dim', 0.0) or 0.0)
            else:
                bright_ft = snap_bright
                dim_ft = snap_dim

            bright_light = bright_ft / feet_per_grid
            dim_light = dim_ft / feet_per_grid

            if (bright_light + dim_light) <= 0.0:
                continue

            light_pos_x, light_pos_y = entity_or_object_pos(entity)

            in_bright, in_dim = light_in_sight(
                pos_x, pos_y, light_pos_x, light_pos_y,
                min_distance=bright_light,
                distance=bright_light + dim_light,
                inclusive=True,
            )

            intensity += 1.0 if in_bright else (0.5 if in_dim else 0.0)

        # Magical darkness sources zero out non-magical light in their area.
        if self.magical_darkness_at(pos_x, pos_y):
            return 0.0

        if self.obscuring_gas_at(pos_x, pos_y):
            intensity = min(intensity, 0.2)

        override = self.tiny_hut_interior(pos_x, pos_y)
        if override is not None:
            return override

        return intensity

    def magical_darkness_at(self, pos_x, pos_y):
        """Return True if any magical-darkness source covers this square."""
        self._ensure_dynamic_sources()
        if not self._darkness_sources:
            return False
        feet_per_grid = self.map.feet_per_grid
        entity_or_object_pos = self.map.entity_or_object_pos
        for entity in self._darkness_sources:
            dark = entity.dark_properties()
            if not dark:
                continue
            radius_squares = dark.get('radius', 0) / feet_per_grid
            if radius_squares <= 0:
                continue
            src_x, src_y = entity_or_object_pos(entity)
            dx = pos_x - src_x
            dy = pos_y - src_y
            # Chebyshev/grid distance — Darkness "spreads around corners",
            # so ignore line-of-sight blocking inside the radius.
            if max(abs(dx), abs(dy)) <= radius_squares:
                return True
        return False

    def obscuring_gas_at(self, pos_x, pos_y):
        """True when a square is inside a heavily obscuring gas cloud."""
        self._ensure_dynamic_sources()
        return (pos_x, pos_y) in self._gas_tiles

    def tiny_hut_domes(self):
        """Cached Tiny Hut objects on this map (empty tuple when none)."""
        self._ensure_dynamic_sources()
        return self._tiny_huts or ()

    def tiny_hut_interior(self, pos_x, pos_y):
        """Return a Tiny Hut interior light override, or None."""
        self._ensure_dynamic_sources()
        for dome in self._tiny_huts or ():
            try:
                if dome.contains((pos_x, pos_y)):
                    override = dome.interior_light_value()
                    if override is not None:
                        return override
            except Exception:
                continue
        return None
