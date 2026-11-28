"""Teleport (PHB 7th-level): personal destination database + d100 outcome.

Covers the destination registry (add/update/remove/familiarity, save/load),
the empty-database cast block, on-target cross-map travel for the caster and
nearby allies, anchor destinations that follow a moving person/object, the
mishap reroll with 3d10 force damage, and the similar-area / off-target
landing helpers.
"""
import random

import pytest
import yaml

from natural20.actions.spell_action import SpellAction
from natural20.map import Map
from natural20.npc import Npc
from natural20.spell.teleport_spell import TeleportSpell
from natural20.utils.teleport_destinations import (
    OUTCOME_MISHAP,
    OUTCOME_OFF_TARGET,
    OUTCOME_ON_TARGET,
    OUTCOME_SIMILAR,
    apply_destination_ops,
    find_destination,
    list_destinations,
    pick_off_target,
    pick_similar_area,
    remove_destination,
    resolve_destination,
    roll_outcome,
    set_familiarity,
    upsert_destination,
)
from tests.ranger_spell_helpers import Arena

SIZE = 16


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _add_map(tmp_path, session, name, themes=None):
    rows = ['.' * SIZE for _ in range(SIZE)]
    doc = {
        'name': name.title(), 'description': 'aux map',
        'map': {'illumination': 1.0, 'base': rows, 'meta': rows},
        'legend': {},
    }
    if themes:
        doc['area_themes'] = list(themes)
    (tmp_path / 'maps' / f'{name}.yml').write_text(yaml.safe_dump(doc))
    battle_map = Map(session, f'maps/{name}')
    session.register_map(name, battle_map)
    return battle_map


def _arena(tmp_path, spells=('teleport',)):
    arena = Arena(tmp_path, caster='wizard', with_battle=True, spells=list(spells))
    arena.caster.spell_slots.setdefault('wizard', {})[7] = 1
    return arena


def _teleport(arena, dest_id, seed=None):
    action = arena.build('teleport', 7, dest_id)
    action.teleport_rng = random.Random(seed)
    action.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(action)
    return action


# ---------------------------------------------------------------------------
# outcome table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("familiarity,roll,expected", [
    ('permanent_circle', 1, OUTCOME_ON_TARGET),
    ('permanent_circle', 100, OUTCOME_ON_TARGET),
    ('linked_object', 1, OUTCOME_ON_TARGET),
    ('very_familiar', 5, OUTCOME_MISHAP),
    ('very_familiar', 6, OUTCOME_SIMILAR),
    ('very_familiar', 13, OUTCOME_SIMILAR),
    ('very_familiar', 14, OUTCOME_OFF_TARGET),
    ('very_familiar', 24, OUTCOME_OFF_TARGET),
    ('very_familiar', 25, OUTCOME_ON_TARGET),
    ('very_familiar', 100, OUTCOME_ON_TARGET),
    ('seen_casually', 33, OUTCOME_MISHAP),
    ('seen_casually', 34, OUTCOME_SIMILAR),
    ('seen_casually', 44, OUTCOME_OFF_TARGET),
    ('seen_casually', 54, OUTCOME_ON_TARGET),
    ('viewed_once', 43, OUTCOME_MISHAP),
    ('viewed_once', 54, OUTCOME_OFF_TARGET),
    ('viewed_once', 74, OUTCOME_ON_TARGET),
    ('false', 50, OUTCOME_MISHAP),
    ('false', 51, OUTCOME_SIMILAR),
    ('false', 100, OUTCOME_SIMILAR),
])
def test_phb_outcome_table(familiarity, roll, expected):
    assert roll_outcome(familiarity, roll) == expected


def test_false_destination_never_on_target():
    assert all(roll_outcome('false', r) != OUTCOME_ON_TARGET for r in range(1, 101))


# ---------------------------------------------------------------------------
# destination registry
# ---------------------------------------------------------------------------

def test_empty_database_blocks_the_spell(tmp_path):
    arena = _arena(tmp_path)
    assert list_destinations(arena.caster) == []
    assert not SpellAction.can_cast(arena.caster, arena.battle, 'teleport')
    upsert_destination(arena.caster, {
        'name': 'Field camp', 'map': 'field', 'x': 8, 'y': 8,
        'familiarity': 'very familiar',
    })
    assert SpellAction.can_cast(arena.caster, arena.battle, 'teleport')


def test_registry_crud_and_familiarity(tmp_path):
    arena = _arena(tmp_path)
    entry = upsert_destination(arena.caster, {
        'name': 'Tower Library', 'map': 'tower', 'x': 3, 'y': 4,
        'familiarity': 'seen casually',
    })
    assert entry['id'] == 'tower-library'
    assert entry['familiarity'] == 'seen_casually'
    # update by id keeps one entry
    upsert_destination(arena.caster, {'id': entry['id'], 'name': 'Tower Library',
                                      'map': 'tower', 'x': 9, 'y': 9,
                                      'familiarity': 'very familiar'})
    assert len(list_destinations(arena.caster)) == 1
    assert find_destination(arena.caster, entry['id'])['x'] == 9
    assert set_familiarity(arena.caster, entry['id'], 'viewed once')['familiarity'] == 'viewed_once'
    assert remove_destination(arena.caster, entry['id'])
    assert list_destinations(arena.caster) == []


def test_destinations_survive_save_load(tmp_path):
    arena = _arena(tmp_path)
    upsert_destination(arena.caster, {
        'name': 'Field camp', 'map': 'field', 'x': 8, 'y': 8,
        'familiarity': 'very familiar',
    })
    upsert_destination(arena.caster, {
        'name': 'Goblin chief (anchor)', 'kind': 'anchor',
        'entity_uid': 'goblin-1', 'familiarity': 'linked object',
    })
    session2, _battle2, _maps2 = arena.round_trip()
    wizard2 = session2.entity_by_uid('wizard')
    saved = list_destinations(wizard2)
    assert len(saved) == 2
    assert {d['familiarity'] for d in saved} == {'very_familiar', 'linked_object'}


# ---------------------------------------------------------------------------
# casting
# ---------------------------------------------------------------------------

def test_cast_without_destinations_fails(tmp_path):
    arena = _arena(tmp_path)
    action = _teleport(arena, 'nowhere', seed=1)
    assert action.result and action.result[0]['type'] == 'teleport_failed'
    assert action.result[0]['reason'] == 'no_known_destination'
    assert arena.session.map_for(arena.caster) is arena.map


def test_on_target_moves_caster_and_allies_cross_map(tmp_path):
    arena = _arena(tmp_path)
    tower = _add_map(tmp_path, arena.session, 'tower')
    dest = upsert_destination(arena.caster, {
        'name': 'Tower', 'map': 'tower', 'x': 5, 'y': 5,
        'familiarity': 'permanent circle',
    })
    action = _teleport(arena, dest['id'], seed=7)
    item = action.result[0]
    assert item['type'] == 'teleport' and item['outcome'] == OUTCOME_ON_TARGET
    # caster lands exactly on the destination square, on the other map
    assert arena.session.map_for(arena.caster) is tower
    assert tower.position_of(arena.caster) == [5, 5]
    # the friendly ally within 10 ft arrives too (nearest free square)
    assert arena.session.map_for(arena.ally) is tower
    assert tower.position_of(arena.ally) == [6, 5]
    # hostile goblins stay behind on the field
    assert arena.map.position_of(arena.goblin) == [6, 2]
    assert arena.map.position_of(arena.goblin2) == [7, 2]


def test_only_visible_nearby_friendlies_arrive(tmp_path):
    arena = _arena(tmp_path)
    _add_map(tmp_path, arena.session, 'tower')
    # far-away ally (> 10 ft away) does not get pulled along
    far = Npc(arena.session, 'goblin', {'name': 'far'})
    arena.session.register_entity(far)
    arena.map.add(far, 15, 15, 'a')  # friendly group, out of range
    dest = upsert_destination(arena.caster, {
        'name': 'Tower', 'map': 'tower', 'x': 5, 'y': 5,
        'familiarity': 'permanent circle',
    })
    action = _teleport(arena, dest['id'], seed=7)
    assert arena.session.map_for(far) is arena.map


def test_anchor_destination_follows_moving_entity(tmp_path):
    arena = _arena(tmp_path)
    tower = _add_map(tmp_path, arena.session, 'tower')
    dest = upsert_destination(arena.caster, {
        'name': 'Goblin warren', 'kind': 'anchor',
        'entity_uid': arena.goblin.entity_uid, 'familiarity': 'linked object',
    })
    # move the anchor (an "object taken from the destination") to the tower
    arena.map.remove(arena.goblin)
    tower.add(arena.goblin, 4, 4, 'b')
    action = _teleport(arena, dest['id'], seed=7)
    item = action.result[0]
    assert item['outcome'] == OUTCOME_ON_TARGET
    assert arena.session.map_for(arena.caster) is tower
    # the anchor square itself is occupied: the caster lands on the nearest
    # free square right beside the goblin
    cx, cy = tower.position_of(arena.caster)
    assert max(abs(cx - 4), abs(cy - 4)) == 1
    # a destroyed anchor no longer resolves: false destination fizzles
    tower.remove(arena.goblin)
    resolved = resolve_destination(arena.session, arena.caster, dest, battle=arena.battle)
    assert resolved is None


def test_mishap_deals_force_damage_and_rerolls(tmp_path, monkeypatch):
    arena = _arena(tmp_path)
    _add_map(tmp_path, arena.session, 'tower')
    dest = upsert_destination(arena.caster, {
        'name': 'Tower', 'map': 'tower', 'x': 5, 'y': 5,
        'familiarity': 'seen casually',
    })
    outcomes = iter([OUTCOME_MISHAP, OUTCOME_ON_TARGET])
    monkeypatch.setattr('natural20.spell.teleport_spell.roll_outcome',
                        lambda familiarity, roll: next(outcomes))
    caster_hp = arena.caster.hit_points()
    action = _teleport(arena, dest['id'], seed=3)
    item = action.result[0]
    assert len(item['rolls']) == 2  # mishap then reroll
    # every teleporting creature took force damage from the mishap
    assert arena.caster.hit_points() < caster_hp
    assert arena.ally.hit_points() < arena.ally.max_hp()
    # and they still arrived after the reroll
    assert item['outcome'] == OUTCOME_ON_TARGET
    assert arena.map.position_of(arena.goblin) == [6, 2]


def test_build_map_lists_known_destinations(tmp_path):
    arena = _arena(tmp_path)
    upsert_destination(arena.caster, {
        'name': 'Tower', 'map': 'tower', 'x': 5, 'y': 5,
        'familiarity': 'very familiar',
    })
    step = TeleportSpell.destination_options(arena.caster)
    assert step == [['Tower (Very familiar)', 'tower']]
    upsert_destination(arena.caster, {
        'id': 'ruins', 'name': 'Dark Ruins', 'map': 'tower', 'x': 1, 'y': 1,
        'familiarity': 'viewed once or described',
    })
    labels = [label for label, _ in TeleportSpell.destination_options(arena.caster)]
    assert 'Dark Ruins (Viewed once or described)' in labels
    action = arena.build('teleport', 7, 'tower')
    assert action.target is arena.caster


# ---------------------------------------------------------------------------
# similar area / off target landing helpers
# ---------------------------------------------------------------------------

def test_similar_area_picks_theme_matching_map(tmp_path):
    arena = _arena(tmp_path)
    _add_map(tmp_path, arena.session, 'lab_b', themes=['laboratory'])
    lab_a = _add_map(tmp_path, arena.session, 'lab_a', themes=['laboratory'])
    _add_map(tmp_path, arena.session, 'tavern_room', themes=['tavern'])
    dest = {
        'id': 'd1', 'name': 'Lost lab', 'kind': 'coords',
        'map': 'lab_b', 'x': 1, 'y': 1, 'familiarity': 'viewed_once',
    }
    landing = pick_similar_area(arena.session, dest, arena.map, rng=random.Random(1))
    assert landing is not None and landing[0] is lab_a  # never the dest map itself


def test_off_target_uses_declared_map(tmp_path):
    arena = _arena(tmp_path)
    road = _add_map(tmp_path, arena.session, 'road')
    dest = {
        'id': 'd1', 'name': 'Tower', 'kind': 'coords', 'map': 'tower',
        'x': 5, 'y': 5, 'familiarity': 'seen_casually',
        'off_target_map': 'road',
    }
    landing = pick_off_target(arena.session, dest, arena.map, rng=random.Random(2))
    assert landing is not None and landing[0] is road
    assert landing[1] >= 0 and landing[2] >= 0


# ---------------------------------------------------------------------------
# game-event / map-trigger granting
# ---------------------------------------------------------------------------

def test_apply_destination_ops_grants_targets_and_once(tmp_path):
    arena = _arena(tmp_path)
    _add_map(tmp_path, arena.session, 'temple')
    grant = {
        'op': 'add', 'target': 'self', 'once': True,
        'destination': {'name': 'Sunken Temple', 'map': 'temple', 'x': 1, 'y': 1,
                        'familiarity': 'viewed once or described'},
    }
    lines, errors = apply_destination_ops(arena.session, [grant], source=arena.caster)
    assert lines and not errors
    assert list_destinations(arena.caster)[0]['familiarity'] == 'viewed_once'
    # once: re-entering the pad does not repeat the narration
    lines2, _ = apply_destination_ops(arena.session, [grant], source=arena.caster)
    assert lines2 == []
    assert len(list_destinations(arena.caster)) == 1
    # party target + remove op
    lines3, _ = apply_destination_ops(arena.session, [{
        'op': 'add', 'target': 'party',
        'destination': {'name': 'Camp', 'map': 'field', 'x': 2, 'y': 2},
    }], source=arena.caster)
    assert list_destinations(arena.ally)
    lines4, _ = apply_destination_ops(arena.session, [{
        'op': 'remove', 'target': 'self',
        'destination': {'name': 'Sunken Temple'},
    }], source=arena.caster)
    assert not find_destination(arena.caster, 'sunken-temple')


def test_map_trigger_grants_destinations(tmp_path):
    arena = _arena(tmp_path)
    _add_map(tmp_path, arena.session, 'temple')
    rows = ['.' * SIZE for _ in range(SIZE)]
    doc = {
        'name': 'Triggered', 'description': 'event map',
        'map': {'illumination': 1.0, 'base': rows, 'meta': rows},
        'legend': {},
        'triggers': {
            'arrival': [{
                'type': 'teleport_destinations',
                'destinations': [{
                    'op': 'add', 'target': 'self',
                    'destination': {'name': 'Temple', 'map': 'temple',
                                    'x': 1, 'y': 1, 'familiarity': 'seen casually'},
                }],
            }],
        },
    }
    (tmp_path / 'maps' / 'triggered.yml').write_text(yaml.safe_dump(doc))
    triggered = Map(arena.session, 'maps/triggered')
    arena.session.register_map('triggered', triggered)
    triggered.activate_map_triggers('arrival', arena.caster, {})
    entry = find_destination(arena.caster, 'temple')
    assert entry is not None and entry['familiarity'] == 'seen_casually'


def test_object_on_enter_grants_destinations(tmp_path):
    from natural20.item_library.object import Object
    arena = _arena(tmp_path)
    _add_map(tmp_path, arena.session, 'ruins')
    pool = Object(arena.session, None, {
        'label': 'Scrying pool',
        'teleport_destinations': [{
            'op': 'add', 'target': 'self', 'once': True,
            'destination': {'name': 'Dark Ruins', 'map': 'ruins',
                            'x': 3, 'y': 3, 'familiarity': 'viewed once'},
        }],
    })
    pool.on_enter(arena.caster, arena.map, arena.battle)
    entry = find_destination(arena.caster, 'dark-ruins')
    assert entry is not None and entry['familiarity'] == 'viewed_once'
    # can cast now (empty-database gate opened by the event)
    assert SpellAction.can_cast(arena.caster, arena.battle, 'teleport')


def test_events_entry_grants_destinations(tmp_path):
    """The documented object-events vocabulary (events: [{event: on_enter,
    teleport_destinations: [...]}]) routes through GenericEventHandler."""
    from natural20.concern.generic_event_handler import GenericEventHandler
    arena = _arena(tmp_path)
    _add_map(tmp_path, arena.session, 'shrine')
    handler = GenericEventHandler(arena.session, arena.map, {
        'event': 'on_enter',
        'teleport_destinations': [{
            'op': 'add', 'target': 'self',
            'destination': {'name': 'Old Shrine', 'map': 'shrine',
                            'x': 2, 'y': 2, 'familiarity': 'described'},
        }],
    })
    handler.handle(arena.caster, {'target': arena.caster, 'battle': arena.battle})
    entry = find_destination(arena.caster, 'old-shrine')
    assert entry is not None and entry['familiarity'] == 'viewed_once'
