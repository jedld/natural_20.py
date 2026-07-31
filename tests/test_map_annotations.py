"""Tests for map landmark annotations."""

from __future__ import annotations

from natural20.map_annotations import (
    annotation_contains_point,
    annotation_label_anchor,
    current_location_annotations_at_position,
    format_current_location_for_llm,
    list_map_annotations,
    normalize_annotation,
    point_in_polygon,
    translate_annotation,
    upsert_map_annotation,
)


def test_point_annotation_normalize():
    ann = normalize_annotation({
        'id': 'Behind_Bar',
        'label': 'Behind the bar',
        'description': 'Staff-only corridor',
        'kind': 'point',
        'pos': [4, 5],
    })
    assert ann['id'] == 'behind_bar'
    assert ann['pos'] == [4, 5]


def test_area_contains_point():
    ann = normalize_annotation({
        'id': 'market',
        'label': 'Market',
        'kind': 'area',
        'bounds': {'x1': 2, 'y1': 2, 'x2': 5, 'y2': 4},
    })
    assert annotation_contains_point(ann, 3, 3)
    assert not annotation_contains_point(ann, 1, 1)


def test_polygon_contains_point():
    ann = normalize_annotation({
        'id': 'yard',
        'label': 'Yard',
        'kind': 'polygon',
        'points': [[0, 0], [4, 0], [4, 4], [0, 4]],
    })
    assert point_in_polygon(2, 2, ann['points'])
    assert not point_in_polygon(5, 5, ann['points'])


def test_upsert_map_annotation_replaces_by_id():
    data = {'map_annotations': [{'id': 'old', 'label': 'Old', 'kind': 'point', 'pos': [1, 1]}]}
    updated = upsert_map_annotation(
        data,
        {'id': 'old', 'label': 'New label', 'kind': 'point', 'pos': [2, 2]},
    )
    items = list_map_annotations(updated)
    assert len(items) == 1
    assert items[0]['label'] == 'New label'
    assert items[0]['pos'] == [2, 2]


def test_translate_point_annotation():
    ann = normalize_annotation({'id': 'tap', 'label': 'Tap', 'kind': 'point', 'pos': [1, 2]})
    moved = translate_annotation(ann, 3, -1)
    assert moved['pos'] == [4, 1]


def test_translate_area_annotation():
    ann = normalize_annotation({
        'id': 'bar',
        'label': 'Bar',
        'kind': 'area',
        'bounds': {'x1': 2, 'y1': 3, 'x2': 5, 'y2': 6},
    })
    moved = translate_annotation(ann, 1, 2)
    assert moved['bounds'] == {'x1': 3, 'y1': 5, 'x2': 6, 'y2': 8}
    assert annotation_label_anchor(ann) == (2, 3)
    assert annotation_label_anchor(moved) == (3, 5)


def test_translate_polygon_annotation():
    ann = normalize_annotation({
        'id': 'yard',
        'label': 'Yard',
        'kind': 'polygon',
        'points': [[0, 0], [2, 0], [2, 2]],
    })
    moved = translate_annotation(ann, 4, 5)
    assert moved['points'] == [[4, 5], [6, 5], [6, 7]]


def test_magical_annotation_fields_preserved():
    ann = normalize_annotation({
        'id': 'glyph',
        'label': 'Arcane glyph',
        'kind': 'point',
        'pos': [1, 2],
        'magical': True,
        'magic_school': 'abjuration',
        'aura_strength': 'strong',
    })
    assert ann['magical'] is True
    assert ann['magic_school'] == 'abjuration'
    assert ann['aura_strength'] == 'strong'


def test_current_location_prefers_area_over_point():
    props = {
        'map_annotations': [
            {
                'id': 'taproom',
                'label': 'Taproom',
                'kind': 'area',
                'bounds': {'x1': 7, 'y1': 16, 'x2': 14, 'y2': 24},
                'description': 'Main common room.',
            },
            {
                'id': 'bar_stool',
                'label': 'Bar stool',
                'kind': 'point',
                'pos': [9, 20],
            },
        ],
    }
    hits = current_location_annotations_at_position(props, 9, 20)
    assert [h['id'] for h in hits] == ['taproom', 'bar_stool']
    line = format_current_location_for_llm(
        hits,
        map_name='town_market',
        position=(9, 20),
    )
    assert line.startswith('Current location on town_market at grid 9,20:')
    assert 'Taproom' in line
    assert 'Main common room' in line


def test_current_location_excludes_stack_opening():
    props = {
        'map_annotations': [
            {
                'id': 'stairs',
                'label': 'Stairs',
                'kind': 'stack_opening',
                'stack': 'tavern',
                'shape': 'point',
                'pos': [9, 16],
            },
            {
                'id': 'taproom',
                'label': 'Taproom',
                'kind': 'area',
                'bounds': {'x1': 7, 'y1': 16, 'x2': 14, 'y2': 24},
            },
        ],
    }
    hits = current_location_annotations_at_position(props, 9, 16)
    assert [h['id'] for h in hits] == ['taproom']


def test_current_location_prefers_smallest_nested_area():
    props = {
        'map_annotations': [
            {
                'id': 'amphail_market',
                'label': 'Market square',
                'kind': 'area',
                'bounds': {'x1': 7, 'y1': 14, 'x2': 20, 'y2': 24},
            },
            {
                'id': 'taproom',
                'label': 'Taproom',
                'kind': 'area',
                'bounds': {'x1': 7, 'y1': 16, 'x2': 14, 'y2': 24},
            },
            {
                'id': 'behind_the_bar',
                'label': 'Behind the bar',
                'kind': 'area',
                'bounds': {'x1': 6, 'y1': 16, 'x2': 10, 'y2': 21},
            },
        ],
    }
    hits = current_location_annotations_at_position(props, 9, 20)
    line = format_current_location_for_llm(hits, map_name='town_market', position=(9, 20))
    assert 'Behind the bar' in line
    assert 'Market square' not in line
    assert 'Taproom' not in line
