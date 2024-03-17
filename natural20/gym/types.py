
from natural20.map_renderer import MapRenderer

class EnvObject:
    def __init__(self, name, type, health, location, weapons, is_enemy = False):
        self.name = name
        self.type = type
        self.health = health
        self.location = location
        self.weapons = weapons
        self.is_enemy = is_enemy

    def __str__(self):
        return f"{self.name} ({self.is_enemy}) is a {self.type} with {self.health * 100}% health at {self.location}"
   
class Environment:
    def __init__(self, map, objects = [], resource = {}):
        map_renderer = MapRenderer(map)
        self.observed_map = map_renderer.render(map)
        self.objects = objects
        self.resource = resource

    def __str__(self):
        return self.observed_map
            