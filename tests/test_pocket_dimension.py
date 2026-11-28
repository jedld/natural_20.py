"""Generic pocket-dimension system: dynamic map creation, entry/exit,
map-set/POV integration, registration cleanup and the dispel anchor."""
from natural20.utils.pocket_dimension import (
    create_pocket_dimension,
    find_pocket_zone,
    iter_pocket_zones,
    pocket_map_properties,
)
from tests.ranger_spell_helpers import Arena


def _open(tmp_path, **kwargs):
    arena = Arena(tmp_path, caster='ranger', with_battle=False)
    opts = dict(name='test_pocket', label='Test Pocket', capacity=2,
                duration_seconds=600, size_ft=20)
    opts.update(kwargs)
    zone = create_pocket_dimension(
        arena.session, arena.caster, None, arena.map, (2, 2), **opts)
    return arena, zone


def test_map_properties_generator():
    props = pocket_map_properties(side_squares=4, label='X')
    assert props['map']['base'] == ['....'] * 4
    assert props['pocket_dimension'] is True


def test_creates_registered_map_in_same_map_set(tmp_path):
    arena, zone = _open(tmp_path)
    pocket = zone.pocket_map()
    assert pocket is not None
    assert arena.session.maps[zone.pocket_map_name] is pocket
    assert arena.session.map_set_for(pocket.name) == arena.session.map_set_for('field')
    # 20 ft @ 5 ft/grid => 4x4 squares
    assert pocket.size == [4, 4]
    # registered for ticking on the outer map (out of combat)
    assert zone in (arena.map.environment_zones or [])
    # session bookkeeping
    assert zone.id in arena.session.session_state['pocket_dimensions']


def test_entrances_on_both_sides(tmp_path):
    arena, zone = _open(tmp_path)
    outer = zone.entrance()
    inner = zone.inner_entrance()
    assert arena.map.position_of(outer) == [2, 2]
    pocket = zone.pocket_map()
    assert pocket.position_of(inner) == [2, 2]
    assert outer.zone is zone and inner.zone is zone
    assert outer.inside is False and inner.inside is True
    assert 'climb_in' in outer.available_interactions(arena.ally)
    assert 'climb_out' in inner.available_interactions(arena.ally)


def test_enter_exit_moves_between_maps(tmp_path):
    arena, zone = _open(tmp_path)
    pos = zone.enter(arena.caster)
    pocket = zone.pocket_map()
    assert arena.session.map_for(arena.caster) is pocket
    assert zone.member_uid_list() == [arena.caster.entity_uid]
    out = zone.exit(arena.caster)
    assert arena.session.map_for(arena.caster) is arena.map
    assert zone.member_uid_list() == []
    assert out is not None


def test_capacity_gating(tmp_path):
    arena, zone = _open(tmp_path, capacity=1)
    zone.enter(arena.caster)
    assert zone.is_full(arena.ally)
    assert zone.is_full(arena.caster) is False  # existing member may re-enter
    details = zone.entrance().available_interactions(arena.ally)['climb_in']
    assert details.get('disabled')


def test_dismiss_ejects_and_unregisters_map(tmp_path):
    arena, zone = _open(tmp_path)
    zone.enter(arena.caster)
    zone.enter(arena.ally)
    zone.dismiss('test')
    assert zone._dismissed
    assert zone.pocket_map() is None
    assert zone.id not in arena.session.session_state['pocket_dimensions']
    for entity in (arena.caster, arena.ally):
        assert arena.session.map_for(entity) is arena.map
    assert [o for o in arena.map.objects_at(2, 2) if getattr(o, 'zone', None) is zone] == []
    assert list(iter_pocket_zones(session=arena.session)) == []
    assert find_pocket_zone(arena.session, zone_id=zone.id) is None


def test_expiry_via_expired_flag(tmp_path):
    arena, zone = _open(tmp_path, duration_seconds=10)
    zone.enter(arena.caster)
    assert not zone.expired()
    arena.session.increment_game_time(15)
    assert zone.expired()
    zone.dismiss()
    assert arena.session.map_for(arena.caster) is arena.map


def test_zone_lives_on_outer_map_for_dispels(tmp_path):
    arena, zone = _open(tmp_path)
    zone.enter(arena.caster)
    # PersistentAoEZone anchor-membership would follow the owner into the
    # pocket; the zone's map must stay the outer one for zones_at/POV logic.
    assert zone.map is arena.map
    assert zone.contains((2, 2))
    assert not zone.contains((0, 0))
