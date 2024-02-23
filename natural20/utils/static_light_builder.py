import numpy as np
class StaticLightBuilder:
    def __init__(self, battlemap):
        self.map = battlemap
        self.properties = battlemap.properties
        self.light_properties = self.properties.get('lights')
        self.light_map = self.properties.get('map', {}).get('light')
        self.base_illumination = self.properties.get('map', {}).get('illumination', 1.0)
        self.lights = []
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
            for y in range(max_y):
                intensity = self.base_illumination
                for light in self.lights:
                    light_pos_x, light_pos_y = light['position']
                    bright_light = light.get('bright', 10) / self.map.feet_per_grid
                    dim_light = light.get('dim', 5) / self.map.feet_per_grid

                    in_bright, in_dim = self.map.light_in_sight(x, y, light_pos_x, light_pos_y, min_distance=bright_light,
                                                                distance=bright_light + dim_light,
                                                                inclusive=False)

                    intensity += 1.0 if in_bright else (0.5 if in_dim else 0.0)

                light_map[x][y] = intensity

        return light_map

    def light_at(self, pos_x, pos_y):
        intensity = 0.0
        for entity in self.map.entities.keys() + self.map.interactable_objects.keys():
            if entity.light_properties is None:
                continue

            light = entity.light_properties
            bright_light = light.get('bright', 0.0) / self.map.feet_per_grid
            dim_light = light.get('dim', 0.0) / self.map.feet_per_grid

            if (bright_light + dim_light) <= 0.0:
                continue

            light_pos_x, light_pos_y = self.map.entity_or_object_pos(entity)

            in_bright, in_dim = self.map.light_in_sight(pos_x, pos_y, light_pos_x, light_pos_y, min_distance=bright_light,
                                                        distance=bright_light + dim_light,
                                                        inclusive=False)

            intensity += 1.0 if in_bright else (0.5 if in_dim else 0.0)

        return intensity
