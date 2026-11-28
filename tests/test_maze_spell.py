"""Maze: the target is banished into a generated labyrinth map with a hostile
minotaur; its Escape action (DC 20 Intelligence) or the zone ending returns it
to the square it vanished from, and the minotaur vanishes with the space."""
from natural20.actions.maze_escape_action import MazeEscapeAction
from natural20.actions.spell_action import SpellAction
from natural20.die_roll import DieRoll
from natural20.environment_zones import tick_environment_zones
from natural20.npc import Npc
from natural20.utils.dispel import end_spell_zone, zone_for_target, zones_at
from natural20.utils.pocket_dimension import find_pocket_zone, iter_pocket_zones
from tests.ranger_spell_helpers import Arena


def _cast(tmp_path, target=None):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['maze'])
    target = target if target is not None else arena.goblin
    arena.cast('maze', 8, target)
    effect = target.effects['maze'][0]['effect']
    zone = next(iter_pocket_zones(session=arena.session))
    return arena, effect, zone


def _force_check(entity, total):
    entity.ability_check = lambda *a, **k: DieRoll.roll(str(total))


def test_yaml_definition(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['maze'])
    details = arena.spell('maze')
    assert details['spell_class'] == 'Natural20::Maze'
    assert details['escape_dc'] == 20
    assert 'minotaur' in details['auto_escape']
    assert details['duration_seconds'] == 600
    assert details['concentration'] is True


def test_can_cast_in_combat(tmp_path):
    arena = Arena(tmp_path, caster='wizard', spells=['maze'])
    arena.caster.spell_slots.setdefault('wizard', {})[8] = 1
    assert SpellAction.can_cast(arena.caster, arena.battle, 'maze')


def test_cast_creates_labyrinth_and_banishes_target(tmp_path):
    arena, effect, zone = _cast(tmp_path)
    pocket = zone.pocket_map()
    assert pocket is not None and pocket.name in arena.session.maps
    assert arena.session.map_set_for(pocket.name) == arena.session.map_set_for('field')
    # a real labyrinth: walls (# auto-stone-walls) and corridors, not an open room
    wall_tiles = sum(row.count('#') for row in pocket.base_map)
    open_tiles = sum(row.count('.') for row in pocket.base_map)
    assert wall_tiles > 0 and open_tiles > 0
    # the goblin lives on the maze map now; the field map no longer holds it
    assert arena.session.map_for(arena.goblin) is pocket
    assert arena.goblin not in arena.map.entities
    # the minotaur warden was spawned on the maze map, group b
    warden = arena.session.entity_by_uid(effect.warden_uid)
    assert warden is not None and warden.kind().lower() == 'minotaur'
    assert arena.session.map_for(warden) is pocket
    assert warden not in zone.members()
    # the doorway is invisible and not climbable
    entrance = zone.entrance()
    assert entrance is not None and entrance.token_image() is None
    assert entrance.available_interactions(arena.caster) == {}
    assert zone.inner_entrance().available_interactions(arena.goblin) == {}
    # escape lands back on the vacated square
    assert zone.return_square == [6, 2]
    assert effect.zone_id == zone.id and effect.pocket_map_name == pocket.name


def test_target_gets_escape_action(tmp_path):
    arena, _effect, _zone = _cast(tmp_path)
    options = MazeEscapeAction.options_for(arena.session, arena.goblin, None)
    assert len(options) == 1
    assert options[0].available(None)


def test_escape_success_returns_to_vacated_square(tmp_path):
    arena, effect, zone = _cast(tmp_path)
    _force_check(arena.goblin, 30)
    # a fresh action (like the web /action route builds it) re-finds the zone
    action = MazeEscapeAction(arena.session, arena.goblin, 'maze_escape')
    action.resolve(arena.session, None, {})
    item = action.result[0]
    assert item['success'] and item['type'] == 'maze_escape'
    assert action.zone is zone and action.maze_effect is effect
    MazeEscapeAction.apply(None, item, arena.session)
    assert zone._dismissed
    assert arena.session.map_for(arena.goblin) is arena.map
    assert arena.map.position_of(arena.goblin) == [6, 2]
    assert not arena.goblin.has_effect('maze')
    # the demiplane is gone and its minotaur vanished with it
    assert zone.pocket_map() is None
    assert arena.session.entity_by_uid(effect.warden_uid) is None
    assert zone.id not in (arena.session.session_state.get('pocket_dimensions') or {})


def test_escape_failure_keeps_the_maze(tmp_path):
    arena, effect, zone = _cast(tmp_path)
    _force_check(arena.goblin, 1)
    action = MazeEscapeAction(arena.session, arena.goblin)
    action.maze_effect = effect
    action.zone = zone
    action.resolve(arena.session, None, {})
    assert not action.result[0]['success']
    MazeEscapeAction.apply(None, action.result[0], arena.session)
    assert not zone._dismissed
    assert arena.session.map_for(arena.goblin) is zone.pocket_map()


def test_minotaur_target_auto_escape(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['maze'])
    bull = Npc(arena.session, 'minotaur', {'name': 'bull'})
    arena.session.register_entity(bull)
    arena.map.add(bull, 9, 9, 'b')
    arena.cast('maze', 8, bull)
    zone = next(iter_pocket_zones(session=arena.session))
    assert bull in zone.members()
    action = MazeEscapeAction.options_for(arena.session, bull, None)[0]
    action.resolve(arena.session, None, {})
    item = action.result[0]
    assert item['auto'] and item['success'] and item['roll'] is None
    MazeEscapeAction.apply(None, item, arena.session)
    assert zone._dismissed
    assert arena.session.map_for(bull) is arena.map


def test_entrance_square_is_the_dispel_target(tmp_path):
    arena, effect, zone = _cast(tmp_path)
    covering = zones_at(None, arena.map, (6, 2))
    assert zone in covering
    assert zone_for_target(zone.entrance(), None, arena.map) is zone
    end_spell_zone(zone)
    assert zone._dismissed
    assert arena.session.map_for(arena.goblin) is arena.map
    assert arena.map.position_of(arena.goblin) == [6, 2]
    assert arena.session.entity_by_uid(effect.warden_uid) is None
    assert not arena.goblin.has_effect('maze')


def test_expiry_collapses_the_labyrinth(tmp_path):
    arena, effect, zone = _cast(tmp_path)
    arena.session.increment_game_time(605)
    tick_environment_zones(arena.session.maps, event_manager=arena.session.event_manager)
    assert zone._dismissed
    assert 'pocket' not in ' '.join(arena.session.maps.keys())
    assert arena.session.map_for(arena.goblin) is arena.map
    assert arena.map.position_of(arena.goblin) == [6, 2]
    assert arena.session.entity_by_uid(effect.warden_uid) is None
    assert not arena.goblin.has_effect('maze')


def test_dismiss_via_caster(tmp_path):
    arena, effect, zone = _cast(tmp_path)
    arena.caster.dismiss_effect(effect)
    assert zone._dismissed
    assert arena.session.map_for(arena.goblin) is arena.map
    assert arena.session.entity_by_uid(effect.warden_uid) is None


def test_save_load_round_trip(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    from natural20.utils.pocket_dimension import PocketDimensionZone
    dump = arena.serialize_all()
    session2, _battle2, maps2 = arena.deserialize(dump)
    goblin2 = session2.entity_by_uid(arena.goblin.entity_uid)
    pocket2 = maps2[zone.pocket_map_name]
    assert session2.map_for(goblin2) is pocket2
    zone2 = find_pocket_zone(session2, zone_id=zone.id, battle=None)
    assert zone2 is not None and isinstance(zone2, PocketDimensionZone)
    assert zone2.map is maps2['field']
    assert zone2.return_square == [6, 2]
    assert zone2.climbable is False
    spell2 = goblin2.effects['maze'][0]['effect']
    assert spell2.zone() is zone2
    # the escape action still works after load
    _force_check(goblin2, 30)
    action = MazeEscapeAction.options_for(session2, goblin2, None)[0]
    action.resolve(session2, None, {})
    MazeEscapeAction.apply(None, action.result[0], session2)
    assert zone2._dismissed
    assert session2.map_for(goblin2) is maps2['field']
    assert maps2['field'].position_of(goblin2) == [6, 2]
