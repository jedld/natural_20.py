"""Tests for magical aura detection helpers."""

from __future__ import annotations

from natural20.map import Map
from natural20.map_annotations import normalize_annotation
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.magical_aura import (
    annotation_magical_auras,
    collect_square_magical_auras,
    entity_magical_auras,
    item_definition_aura,
    list_campaign_magical_annotations,
    magical_auras_for_tile,
    viewer_has_detect_magic,
)


def _session():
    return Session(root_path='tests/fixtures')


def test_item_scroll_has_evocation_aura():
    session = _session()
    item_def = session.load_thing('scroll_of_magic_missile')
    aura = item_definition_aura(session, 'scroll_of_magic_missile', item_def)
    assert aura is not None
    assert aura['school'] == 'evocation'


def test_annotation_magical_fields_normalize():
    ann = normalize_annotation({
        'id': 'rose',
        'label': 'Bound rose',
        'kind': 'point',
        'pos': [2, 3],
        'magical': True,
        'magic_school': 'transmutation',
        'aura_strength': 'strong',
    })
    auras = annotation_magical_auras(ann)
    assert len(auras) == 1
    assert auras[0]['school'] == 'transmutation'
    assert auras[0]['strength'] == 'strong'


def test_entity_property_magical_aura():
    session = _session()
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    mage.properties['magical_aura'] = {
        'school': 'evocation',
        'label': 'Arcane focus',
        'strength': 'faint',
    }
    auras = entity_magical_auras(session, mage)
    assert any(a['school'] == 'evocation' for a in auras)


def test_detect_magic_only_reveals_auras_in_range():
    session = _session()
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    battle_map = Map(session, 'battle_sim_objects')
    battle_map.session.game_properties = {
        'magical_annotations': {
            'Warehouse': [{
                'id': 'far_aura',
                'label': 'Distant relic',
                'kind': 'point',
                'pos': [20, 20],
                'magical': True,
                'magic_school': 'necromancy',
            }],
        },
    }
    mage.register_effect('detect_magic', object(), effect='detect_magic', duration=600)
    mage_pos = (0, 5)
    battle_map.entities[mage] = mage_pos

    near = magical_auras_for_tile(session, battle_map, mage_pos[0], mage_pos[1], [mage])
    far = magical_auras_for_tile(session, battle_map, 20, 20, [mage])

    assert viewer_has_detect_magic(mage)
    assert isinstance(near, list)
    assert far == []


def test_detect_magic_reveals_auras_without_line_of_sight():
    from natural20.web.json_renderer import JsonRenderer
    from natural20.utils.magical_aura import detect_magic_path_blocked, distance_ft

    session = _session()
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    battle_map = Map(session, 'battle_sim_objects')
    mage_pos = (1, 6)
    battle_map.entities[mage] = mage_pos
    mage.register_effect('detect_magic', object(), effect='detect_magic', duration=600)

    hidden_pos = None
    for x in range(battle_map.size[0]):
        for y in range(battle_map.size[1]):
            if (x, y) == mage_pos:
                continue
            if battle_map.can_see_square(mage, (x, y)):
                continue
            if distance_ft(mage_pos, (x, y)) > 30:
                continue
            if detect_magic_path_blocked(battle_map, mage_pos, (x, y)):
                continue
            hidden_pos = (x, y)
            break
        if hidden_pos:
            break
    assert hidden_pos is not None, 'fixture map needs a square within 30 ft, out of LOS, and not barrier-blocked'

    session.game_properties = {
        'magical_annotations': {
            'Warehouse': [{
                'id': 'hidden_glyph',
                'label': 'Hidden curse',
                'kind': 'point',
                'pos': list(hidden_pos),
                'magical': True,
                'magic_school': 'necromancy',
            }],
        },
    }

    tiles = JsonRenderer(battle_map).render(entity_pov=[mage])
    sensed = None
    for x_row in tiles:
        for tile in x_row:
            if isinstance(tile, dict) and tile.get('x') == hidden_pos[0] and tile.get('y') == hidden_pos[1]:
                sensed = tile
                break
        if sensed:
            break
    assert sensed is not None
    assert sensed.get('detect_magic_sense') is True
    assert sensed.get('line_of_sight') is False
    auras = sensed.get('magical_auras') or []
    assert len(auras) == 1
    assert auras[0].get('revelation') == 'presence'
    assert auras[0].get('school') == 'unknown'
    assert auras[0].get('label') == 'Magic sensed'


def test_detect_magic_reveals_school_when_target_visible():
    session = _session()
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    battle_map = Map(session, 'battle_sim_objects')
    mage_pos = (1, 6)
    battle_map.entities[mage] = mage_pos
    mage.register_effect('detect_magic', object(), effect='detect_magic', duration=600)

    npc = battle_map.entity_at(5, 5)
    assert npc is not None
    npc.properties['magical_aura'] = {
        'school': 'evocation',
        'label': 'Arcane focus',
        'strength': 'faint',
    }
    assert battle_map.can_see_square(mage, (5, 5))

    auras = magical_auras_for_tile(session, battle_map, 5, 5, [mage])
    assert len(auras) == 1
    assert auras[0].get('revelation') == 'aura'
    assert auras[0].get('school') == 'evocation'


def test_detect_magic_blocked_by_stone_wall():
    from natural20.utils.magical_aura import detect_magic_path_blocked

    session = _session()
    battle_map = Map(session, 'battle_sim_objects')
    # Warehouse row y=4 is mostly stone (#=######); sensing across it should fail.
    assert detect_magic_path_blocked(battle_map, (1, 6), (6, 2))
    assert not detect_magic_path_blocked(battle_map, (1, 6), (1, 5))


def test_detect_magic_path_through_door_object_wall_does_not_crash():
    """Regression: DoorObjectWall.opaque() requires origin; barrier checks must not call it bare."""
    from natural20.item_library.door_object import DoorObjectWall
    from natural20.utils.magical_aura import _barrier_layers_at_square, detect_magic_path_blocked
    from natural20.web.json_renderer import JsonRenderer

    session = _session()
    battle_map = Map(session, 'battle_sim_objects')
    door_props = session.load_object('door_l')
    door_props['type'] = 'door_l'
    door = DoorObjectWall(session, battle_map, door_props)
    battle_map.place_object(door, 3, 5)

    assert door.closed()
    layers = _barrier_layers_at_square(battle_map, 3, 5, origin=None)
    assert any(material == 'wood' for material, _ in layers)

    # Must not raise TypeError from opaque(None).
    assert detect_magic_path_blocked(battle_map, (1, 6), (5, 5)) is False

    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    mage_pos = (1, 6)
    battle_map.entities[mage] = mage_pos
    mage.register_effect('detect_magic', object(), effect='detect_magic', duration=600)

    tiles = JsonRenderer(battle_map).render(entity_pov=[mage])
    assert isinstance(tiles, list)


def test_campaign_magical_annotations_merge_on_square():
    session = _session()
    battle_map = Map(session, 'battle_sim_objects')
    session.game_properties = {
        'magical_annotations': {
            'Warehouse': [{
                'id': 'hidden_glyph',
                'label': 'Hidden glyph',
                'kind': 'point',
                'pos': [4, 5],
                'magical': True,
                'magic_school': 'abjuration',
            }],
        },
    }
    auras = collect_square_magical_auras(session, battle_map, 4, 5)
    assert any(a['school'] == 'abjuration' for a in auras)
    assert list_campaign_magical_annotations(session, 'Warehouse')
