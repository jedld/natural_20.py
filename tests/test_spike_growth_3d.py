"""Spike Growth zone squares must reach the 3D VTT as thorns terrain fixtures."""
from natural20.web.map_state import classify_object_kind, objects_from_tiles


def test_spike_growth_tile_classifies_as_thorns():
    assert classify_object_kind({'type': 'spike_growth_tile', 'name': 'Spike Growth'}) == 'thorns'


def test_spike_growth_tile_reaches_3d_objects():
    """Zone tiles have no fixture image but must still appear in map_state objects."""
    tiles = [{
        'x': 2,
        'y': 3,
        'objects': [{
            'id': 'spike_growth_tile:abc',
            'name': 'Spike Growth',
            'type': 'spike_growth_tile',
            'image': None,
        }],
    }]
    objects = objects_from_tiles(tiles)
    assert len(objects) == 1
    entry = objects[0]
    assert entry['kind'] == 'thorns'
    assert entry['x'] == 2 and entry['y'] == 3
