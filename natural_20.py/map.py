class Terrain():
    def __init__(self, name, passable, movement_cost, symbol=None):
        self.name = name
        self.passable = passable
        self.movement_cost = movement_cost
        self.symbol = symbol if symbol else name[0].upper()

    def symbol(self):
        return self.symbol

def dirt():
    return Terrain("dirt", True, 1.0)

class Map():
    def __init__(self, width, height, default_base_terrain = dirt()):
        self.width = width
        self.height = height

        self.tiles = self.initialize_tiles(default_base_terrain)
    
    def initialize_tiles(self, default_base_terrain):
        map_layer = []
        terrain = []
        map_layer.append(default_base_terrain) # map layer for terrain

        for _ in range(0, self.width):
            row = []
            for _ in range(0, self.height):
                row.append(None)
            terrain.append(row)

        return self.map_layer
    
    def get_tile(self, x, y):
        return self.tiles[x][y]
    
    def __str__(self) -> str:
        for row in self.tiles:
            for cell in row:
                if cell == None:
                    print(" ", end="")
                else:
                    print(cell.symbol, end="")
# Path: natural_20.py/agent.py
    
