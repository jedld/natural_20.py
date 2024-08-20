import pdb
class MapRenderer:
    DEFAULT_TOKEN_COLOR = 'cyan'

    def __init__(self, map, battle=None):
        self.map = map
        self.battle = battle

    def render(self, entity=None, line_of_sight=None, path=[], acrobatics_checks=[], athletics_checks=[], select_pos=None,
               update_on_drop=True, sight_range=None, range_cutoff=False, path_char=None, highlight={}, viewport_size=None, top_position=[0, 0]):
        highlight_positions = [pos for e in highlight.keys() for pos in self.map.entity_squares(e)]

        viewport_size = viewport_size or self.map.size

        top_x, top_y = top_position

        right_x = min(top_x + viewport_size[0] - 1, self.map.size[0] - 1)
        right_y = min(top_y + viewport_size[1] - 1, self.map.size[1] - 1)

        rendered_map = []
        for row_index in range(top_y, right_y + 1):
            row = []
            for col_index in range(top_x, right_x + 1):
                c = self.map.base_map[col_index][row_index]
                display = self.render_position(c, col_index, row_index, path=path,
                                               override_path_char=path_char,
                                               entity=entity,
                                               line_of_sight=line_of_sight,
                                               update_on_drop=update_on_drop,
                                               acrobatics_checks=acrobatics_checks,
                                               athletics_checks=athletics_checks)

                if [col_index, row_index] in highlight_positions:
                    display = display.replace('\033[0m', '\033[48;5;9m')

                if select_pos and select_pos == [col_index, row_index]:
                    display = display.replace('\033[0m', '\033[48;5;15m')

                if sight_range and entity and self.map.line_distance(entity, col_index, row_index) > sight_range:
                    if range_cutoff:
                        display = ' '
                    else:
                        display = display.replace('\033[0m', '\033[48;5;9m')

                if display is None:
                    pdb.set_trace()
                if not isinstance(display, str):
                    pdb.set_trace()
                row.append(display)
            rendered_map.append(''.join(row))
        return '\n'.join(rendered_map) + '\n'

    def render_light(self, pos_x, pos_y):
        intensity = self.map.light_at(pos_x, pos_y)
        if intensity >= 1.0:
            return 'yellow'
        elif intensity >= 0.5:
            return 'black'
        else:
            return 'black'

    def object_token(self, pos_x, pos_y):
        object_meta = self.map.object_at(pos_x, pos_y)
        if not object_meta:
            return None

        m_x, m_y = self.map.interactable_objects[object_meta]

        if not object_meta.token():
            return None
        if object_meta.token() == 'inherit':
            return 'inherit'

        if isinstance(object_meta.token(), list):
            return object_meta.token()[pos_y - m_y][pos_x - m_x]
        else:
            return object_meta.token()

    def npc_token(self, pos_x, pos_y):
        entity = self.tokens[pos_x][pos_y]
        # color = entity['entity'].color or self.DEFAULT_TOKEN_COLOR
        return self.token(entity, pos_x, pos_y)

    def render_position(self, c, col_index, row_index, path=[], override_path_char=None, entity=None, line_of_sight=None, update_on_drop=True, acrobatics_checks=[],
                        athletics_checks=[]):
        background_color = self.render_light(col_index, row_index)
        default_ground = '·'

        token = self.object_token(col_index, row_index)
        if token:
            if not token == 'inherit':
                c = token or default_ground
        else:
            c = default_ground

        token = c
        if self.tokens[col_index][row_index] and self.tokens[col_index][row_index]['entity'].dead():
            token = '`'
        elif self.tokens[col_index][row_index]:
            if line_of_sight is None or self.any_line_of_sight(line_of_sight, self.tokens[col_index][row_index]['entity']):
                token = self.npc_token(col_index, row_index)

        if path and (override_path_char is None or path[0] != [col_index, row_index]):
            if [col_index, row_index] in path:
                path_char = override_path_char or token
                path_color = 'red' if entity and self.map.jump_required(entity, col_index, row_index) else 'blue'
                if [col_index, row_index] in athletics_checks or [col_index, row_index] in acrobatics_checks:
                    path_char = '✓'

                colored_path = path_char
                if path[0] == [col_index, row_index]:
                    colored_path = colored_path.blink()
                return colored_path

            if line_of_sight and not self.location_is_visible(update_on_drop, col_index, row_index, path):
                return ' '
        else:
            has_line_of_sight = False
            if isinstance(line_of_sight, list):
                has_line_of_sight = any(self.map.can_see_square(l, (col_index, row_index)) for l in line_of_sight)
            elif line_of_sight:
                has_line_of_sight = self.map.can_see_square(line_of_sight, (col_index, row_index))

            if line_of_sight and not has_line_of_sight:
                return ' '

        return token

    def location_is_visible(self, update_on_drop, pos_x, pos_y, path):
        if not update_on_drop:
            return self.map.line_of_sight(path[-1][0], path[-1][1], pos_x, pos_y, inclusive=False)

        return self.map.line_of_sight(path[-1][0], path[-1][1], pos_x, pos_y, distance=1, inclusive=False) or \
               self.map.line_of_sight(path[0][0], path[0][1], pos_x, pos_y, inclusive=False)

    def any_line_of_sight(self, line_of_sight, entity):
        if self.battle is None:
            return True

        if isinstance(line_of_sight, list):
            return any(self.battle.can_see(l, entity) for l in line_of_sight)
        else:
            return self.battle.can_see(line_of_sight, entity)

    def token(self, entity, pos_x, pos_y):
        if entity['entity'].token():
            m_x, m_y = self.map.entities[entity['entity']]
            try:
                return entity['entity'].token()[pos_x - m_x][pos_y - m_y]
            except:
                pdb.set_trace()
        else:
            return self.map.tokens[pos_x][pos_y]['token']

    @property
    def tokens(self):
        return self.map.tokens
