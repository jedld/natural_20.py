import yaml

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
    def __init__(self, map_file_path):
        self.terrain = {}
        self.map = []
        self.properties = self.load(map_file_path)
        base = self.properties.get('map', {}).get('base', [])
        self.size = [len(base[0]), len(base)]
        self.base_map = []
        self.objects = []
        self.tokens = []
        self.entities = {}  # Assuming entities is a dictionary
        
        for _ in range(self.size[1]):
            row = []
            for _ in range(self.size[0]):
                row.append(None)
            self.base_map.append(row)

        for _ in range(self.size[1]):
            row = []
            for _ in range(self.size[0]):
                row.append([])
            self.objects.append(row)

        for _ in range(self.size[1]):
            row = []
            for _ in range(self.size[0]):
                row.append([])
            self.tokens.append(row)


    def load(self, map_file_path):
        with open(map_file_path, 'r') as file:
            data = yaml.safe_load(file)
            return data

    def place(self, position, entity, token=None, battle=None):
        pos_x, pos_y = position

        if entity is None:
            raise ValueError('entity param is required')

        entity_data = {'entity': entity, 'token': token or entity.name}
        self.tokens[pos_x][pos_y] = entity_data
        self.entities[entity] = [pos_x, pos_y]

        source_token_size = entity.token_size()

        for ofs_x in range(source_token_size):
            for ofs_y in range(source_token_size):
                self.tokens[pos_x + ofs_x][pos_y + ofs_y] = entity_data

    def object_at(self, pos_x, pos_y, reveal_concealed=False):
        objects_at_position = self.objects[pos_x][pos_y]
        for obj in objects_at_position:
            if reveal_concealed or not obj.concealed():
                return obj
        return None
