import numpy as np
class StaticLightBuilder:
    def __init__(self, battlemap):
        self.map = battlemap
        self.properties = battlemap.properties
        self.size = battlemap.size
        self.light_properties = self.properties.get('lights')
        self.light_map = self.properties.get('map', {}).get('light')
        self.base_illumination = self.properties.get('map', {}).get('illumination', 1.0)
        manual_light_map = self.properties.get('map', {}).get('light_map',[])
        self.lights = []
        self.fixed_lights = []

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

    def build_map(self):
        max_x, max_y = self.map.size

        light_map = np.full((max_x, max_y), self.base_illumination)
        for x in range(max_x):
            for index_2 in range(max_y):
                y = max_y - index_2 - 1
                intensity = self.base_illumination
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

    def light_at(self, pos_x, pos_y):
        intensity = 0.0
        feet_per_grid = self.map.feet_per_grid
        light_in_sight = self.map.light_in_sight
        entity_or_object_pos = self.map.entity_or_object_pos

        # Iterate entities + objects directly without building an intermediate
        # list (the previous '+=' on .keys() views triggered MutableMapping
        # abc iteration that dominated /update CPU time).
        for source in (self.map.entities, self.map.interactable_objects):
            for entity in source:
                light = entity.light_properties()
                if light is None:
                    continue

                bright_light = light.get('bright', 0.0) / feet_per_grid
                dim_light = light.get('dim', 0.0) / feet_per_grid

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

        return intensity

    def magical_darkness_at(self, pos_x, pos_y):
        """Return True if any magical-darkness source covers this square."""
        feet_per_grid = self.map.feet_per_grid
        entity_or_object_pos = self.map.entity_or_object_pos
        for source in (self.map.entities, self.map.interactable_objects):
            for entity in source:
                if not hasattr(entity, 'dark_properties'):
                    continue
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
