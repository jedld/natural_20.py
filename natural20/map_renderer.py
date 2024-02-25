import pdb
class MapRenderer:
    DEFAULT_TOKEN_COLOR = 'cyan'

    def __init__(self, map, battle=None):
        self.map = map
        self.battle = battle

    def render(self, entity=None, line_of_sight=None, path=[], acrobatics_checks=[], athletics_checks=[], select_pos=None,
               update_on_drop=True, range_cutoff=False, path_char=None, highlight={}, viewport_size=None, top_position=[0, 0]):
        highlight_positions = [pos for e in highlight.keys() for pos in self.map.entity_squares(e)]

        viewport_size = viewport_size or self.map.size

        top_x, top_y = top_position

        right_x = min(top_x + viewport_size[0] - 1, self.map.size[0] - 1)
        right_y = min(top_y + viewport_size[1] - 1, self.map.size[1] - 1)

        rendered_map = []
        for col_index in range(top_x, right_x + 1):
          row_data = []
          for row_index in range(top_y, right_y + 1):
              row_data.append(self.render_position(' ', col_index, row_index, path, path_char, entity, line_of_sight, update_on_drop, acrobatics_checks, athletics_checks))
          rendered_map.append(''.join([ x if x is not None else ' ' for x in row_data]))
        return '\n'.join(rendered_map)

    def render_light(self, pos_x, pos_y):
        return 1.0
        
    def render_position(self, c, col_index, row_index, path=[], override_path_char=None, entity=None, line_of_sight=None, update_on_drop=True, acrobatics_checks=[],
                        athletics_checks=[]):
        default_ground = '.'
        token = self.object_token(col_index, row_index)
        if token:
            c = token if token != "inherit" else c
        else:
            c = default_ground

        token_data = self.tokens()[col_index][row_index]

        if token_data and 'entity' in token_data:
          entity_token = self.tokens()[col_index][row_index].get('entity')
        else:
          entity_token = None

        if entity_token and entity_token.dead():
            token = '`'  # Assuming a method to colorize this string
        elif entity_token:
            if line_of_sight is None or self.any_line_of_sight(line_of_sight, entity_token):
                token = self.npc_token(col_index, row_index)
        else:
            token = c

        if path and not (override_path_char is None and path[0] == [col_index, row_index]):
            if [col_index, row_index] in path:
                path_char = override_path_char or token
                path_color = 'red' if entity and self.map.jump_required(entity, col_index, row_index) else 'blue'
                if [col_index, row_index] in athletics_checks or [col_index, row_index] in acrobatics_checks:
                    path_char = "\u2713"
                colored_path = path_char  # Assuming a method to colorize this string
                return colored_path
            if line_of_sight and not self.location_is_visible(update_on_drop, col_index, row_index, path):
                return ' '  # Assuming a method to colorize this string
        else:
            has_line_of_sight = False
            if isinstance(line_of_sight, list):
                for l in line_of_sight:
                    if self.map.can_see_square(l, col_index, row_index):
                        has_line_of_sight = True
                        break
            elif line_of_sight and self.map.can_see_square(line_of_sight, col_index, row_index):
                has_line_of_sight = True

            if line_of_sight and not has_line_of_sight:
                return ' '  # Assuming a method to colorize this string

        return token

    def object_token(self, pos_x, pos_y):
        object_meta = self.map.object_at(pos_x, pos_y)
        if not object_meta:
            return None

        m_x, m_y = self.map.interactable_objects[object_meta]
        color = object_meta.get('color') or self.DEFAULT_TOKEN_COLOR

        if not object_meta.get('token'):
            return None
        if object_meta['token'] == 'inherit':
            return 'inherit'

        if isinstance(object_meta['token'], list):
            # Assuming a method to colorize this string similarly to Ruby's colorize
            return self.colorize(object_meta['token'][pos_y - m_y][pos_x - m_x], color)
        else:
            # Assuming a method to colorize this string
            return self.colorize(object_meta['token'], color)

    def colorize(self, text, color):
        return text
    
    def tokens(self):
        return self.map.tokens
    
    def npc_token(self, pos_x, pos_y):
      entity = self.tokens()[pos_x][pos_y]
      return self.token(entity, pos_x, pos_y)

    def token(self, entity, pos_x, pos_y):

        if entity['entity'].token!=None:
            m_x, m_y = self.map.entities[entity['entity']]
            return entity['entity'].token()[pos_y - m_y][pos_x - m_x]
        else:
            return self.map.tokens()[pos_x][pos_y]['token']

        