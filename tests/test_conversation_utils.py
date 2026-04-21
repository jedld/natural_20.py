from natural20.utils.conversation import audible_entities, conversation_reachability, mention_handle_for, resolve_mention_targets


class FakeEntity:
    def __init__(self, entity_uid, name, passive_perception=10, conversable=True):
        self.entity_uid = entity_uid
        self.name = name
        self._passive_perception = passive_perception
        self._conversable = conversable

    def label(self):
        return self.name

    def passive_perception(self):
        return self._passive_perception

    def conversable(self):
        return self._conversable


class FakeDoor:
    def __init__(self, opened=False):
        self._opened = opened

    def kind_of_door(self):
        return True

    def opened(self):
        return self._opened

    def dead(self):
        return False


class FakeWallObject:
    def wall(self):
        return True

    def opaque(self, origin=None):
        return True


class FakeMap:
    feet_per_grid = 5

    def __init__(self, positions, objects=None, walls=None):
        self.positions = {
            entity: self._normalize_position(position)
            for entity, position in positions.items()
        }
        self.objects = objects or {}
        self.walls = set(walls or [])

    def _normalize_position(self, position):
        if isinstance(position, tuple):
            return position
        return (position, 0)

    def entities_in_range(self, source, range_ft):
        return [
            entity for entity in self.positions
            if entity != source and self.distance(source, entity) * self.feet_per_grid <= range_ft
        ]

    def distance(self, source, target):
        source_pos = self.positions[source]
        target_pos = self.positions[target]
        return abs(source_pos[0] - target_pos[0]) + abs(source_pos[1] - target_pos[1])

    def position_of(self, entity):
        return self.positions[entity]

    def squares_in_path(self, pos1_x, pos1_y, pos2_x, pos2_y, inclusive=True):
        path = []
        x_step = 1 if pos2_x >= pos1_x else -1
        y_step = 1 if pos2_y >= pos1_y else -1

        for current_x in range(pos1_x, pos2_x + x_step, x_step):
            path.append((current_x, pos1_y))
        for current_y in range(pos1_y + y_step, pos2_y + y_step, y_step):
            path.append((pos2_x, current_y))

        if not inclusive and path and path[-1] == (pos2_x, pos2_y):
            path.pop()
        return path

    def wall(self, pos_x, pos_y):
        return (pos_x, pos_y) in self.walls

    def objects_at(self, pos_x, pos_y):
        return list(self.objects.get((pos_x, pos_y), []))


def test_audible_entities_respect_listener_passive_perception_bonus():
    speaker = FakeEntity('speaker', 'Speaker')
    sharp_listener = FakeEntity('sharp', 'Sharp Listener', passive_perception=15)
    dull_listener = FakeEntity('dull', 'Dull Listener', passive_perception=10)
    battle_map = FakeMap({
        speaker: 0,
        sharp_listener: 7,
        dull_listener: 7,
    })

    audible = audible_entities(speaker, battle_map, distance_ft=30)
    audible_ids = [entry['entity'].entity_uid for entry in audible]

    assert 'sharp' in audible_ids
    assert 'dull' not in audible_ids


def test_resolve_mention_targets_supports_handles_and_unique_name_parts():
    thorn = FakeEntity('thorn_durst', 'Thorn Durst')
    rose = FakeEntity('rose_durst', 'Rose Durst')

    resolved = resolve_mention_targets(
        f"@thorn keep quiet and @{mention_handle_for(rose)} stay close",
        [thorn, rose],
    )

    assert [entity.entity_uid for entity in resolved] == ['thorn_durst', 'rose_durst']


def test_conversation_reachability_marks_entities_that_need_a_louder_reply():
    speaker = FakeEntity('speaker', 'Speaker')
    distant_listener = FakeEntity('listener', 'Distant Listener', passive_perception=10)
    battle_map = FakeMap({
        speaker: 0,
        distant_listener: 10,
    })

    entries = conversation_reachability(speaker, battle_map, mode='normal')
    assert len(entries) == 1
    entry = entries[0]

    assert entry['entity'].entity_uid == 'listener'
    assert entry['reachable_now'] is False
    assert entry['reachable_with_shout'] is True
    assert entry['minimum_volume'] == 'shout'
    assert entry['status'] == 'requires_louder_voice'


def test_conversation_reachability_marks_entities_that_are_too_far_to_reply():
    speaker = FakeEntity('speaker', 'Speaker')
    far_listener = FakeEntity('listener', 'Far Listener', passive_perception=0)
    battle_map = FakeMap({
        speaker: 0,
        far_listener: 15,
    })

    entries = conversation_reachability(speaker, battle_map, mode='shout')
    assert len(entries) == 1
    entry = entries[0]

    assert entry['reachable_now'] is False
    assert entry['reachable_with_shout'] is False
    assert entry['minimum_volume'] is None
    assert entry['status'] == 'too_far'


def test_conversation_reachability_applies_closed_door_acoustic_penalty():
    speaker = FakeEntity('speaker', 'Speaker')
    listener = FakeEntity('listener', 'Listener', passive_perception=10)
    battle_map = FakeMap(
        {
            speaker: (0, 0),
            listener: (5, 0),
        },
        objects={(3, 0): [FakeDoor(opened=False)]},
    )

    entries = conversation_reachability(speaker, battle_map, mode='normal')
    entry = entries[0]

    assert entry['distance_ft'] == 25
    assert entry['adjusted_distance_ft'] == 35
    assert entry['acoustic_penalty_ft'] == 10
    assert entry['closed_doors'] == 1
    assert entry['status'] == 'requires_louder_voice'
    assert entry['minimum_volume'] == 'shout'
    assert entry['acoustic_summary'] == '1 closed door'


def test_conversation_reachability_applies_wall_acoustic_penalty():
    speaker = FakeEntity('speaker', 'Speaker')
    listener = FakeEntity('listener', 'Listener', passive_perception=10)
    battle_map = FakeMap(
        {
            speaker: (0, 0),
            listener: (10, 0),
        },
        objects={(5, 0): [FakeWallObject()]},
        walls={(5, 0)},
    )

    entries = conversation_reachability(speaker, battle_map, mode='shout')
    entry = entries[0]

    assert entry['distance_ft'] == 50
    assert entry['adjusted_distance_ft'] == 70
    assert entry['acoustic_penalty_ft'] == 20
    assert entry['walls'] == 1
    assert entry['status'] == 'too_far'
    assert entry['minimum_volume'] is None
    assert entry['acoustic_summary'] == '1 wall tile'