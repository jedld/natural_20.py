"""Rope Trick: the party climbs a map rope into a generated pocket-dimension
map; nothing outside can reach them; dispel/expiry/dismiss spills everyone
back out next to the rope."""
from natural20.actions.spell_action import SpellAction
from natural20.spell.rope_trick_spell import RopeTrickSpell
from natural20.utils.action_restrictions import is_restricted
from natural20.utils.dispel import end_spell_zone, zone_for_target, zones_at
from natural20.utils.pocket_dimension import find_pocket_zone, iter_pocket_zones
from tests.ranger_spell_helpers import Arena


def _cast(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['rope_trick'])
    arena.cast('rope_trick', 2)
    effect = arena.caster.effects['rope_trick'][0]['effect']
    zone = next(iter_pocket_zones(session=arena.session))
    return arena, effect, zone


def test_yaml_definition(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['rope_trick'])
    details = arena.spell('rope_trick')
    assert details['spell_class'] == 'Natural20::RopeTrick'
    assert 'out_of_combat' in details['requires']
    assert details['max_creatures'] == 8
    assert details['pocket_size_ft'] == 30


def test_cannot_cast_during_combat(tmp_path):
    arena = Arena(tmp_path, caster='wizard', spells=['rope_trick'])
    assert not SpellAction.can_cast(arena.caster, arena.battle, 'rope_trick')


def test_can_cast_out_of_combat(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['rope_trick'])
    assert SpellAction.can_cast(arena.caster, None, 'rope_trick')


def test_cast_creates_pocket_map_and_moves_members(tmp_path):
    arena, effect, zone = _cast(tmp_path)
    pocket = zone.pocket_map()
    assert pocket is not None and pocket.name in arena.session.maps
    # same map set as the entry map so POV/lookup keep working
    assert arena.session.map_set_for(pocket.name) == arena.session.map_set_for('field')
    # caster + ally climbed in; the goblin stays outside
    assert pocket.entity_at(*pocket.position_of(arena.caster)) is arena.caster
    assert arena.session.map_for(arena.caster) is pocket
    assert arena.session.map_for(arena.ally) is pocket
    assert arena.goblin in arena.map.entities
    assert zone.member_uid_list() == [arena.caster.entity_uid, arena.ally.entity_uid]
    # the spell remembers its zone
    assert effect.zone_id == zone.id and effect.pocket_map_name == pocket.name


def test_rope_entrance_object_on_outer_map(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    entrance = zone.entrance()
    assert entrance is not None
    assert arena.map.position_of(entrance) == [2, 2]
    assert entrance.token_image() == 'objects/rope_trick.png'
    assert not entrance.allow_targeting()  # the rope itself is not an attack target
    assert entrance.available_interactions(arena.goblin)['climb_in']  # outsider sees the verb


def test_members_hidden_and_restricted(tmp_path):
    arena, _effect, _zone = _cast(tmp_path)
    for member in (arena.caster, arena.ally):
        assert not member.allow_targeting()
        assert is_restricted(member, 'attack') and is_restricted(member, 'spell')
    assert arena.goblin.allow_targeting()
    assert not arena.goblin.has_effect('rope_trick')


def test_outside_cannot_target_members(tmp_path):
    """Members are on a different map: AoE gathering and thing_at never see them."""
    arena, _effect, zone = _cast(tmp_path)
    assert any(getattr(o, 'zone', None) is zone for o in arena.map.objects_at(2, 2))
    for square in arena.map.squares_in_radius((2, 2), 15, require_los=False):
        assert arena.map.entity_at(*square) is not arena.caster
    assert arena.map.entity_at(2, 2) is None


def test_member_cap(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['rope_trick'])
    spell = RopeTrickSpell(arena.session, arena.caster, 'RopeTrickSpell',
                           dict(arena.spell('rope_trick'), max_creatures=1))
    assert spell.members_for(arena.caster) == [arena.caster]


def test_climb_out_and_back_in(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    inner = zone.inner_entrance()
    assert 'climb_out' in inner.available_interactions(arena.ally)
    inner.use(arena.ally, {'action': 'climb_out', 'battle': None}, arena.session)
    assert arena.session.map_for(arena.ally) is arena.map
    assert arena.ally.entity_uid not in zone.member_uid_list()
    # standing next to the rope, the ally can climb back in
    entrance = zone.entrance()
    assert 'climb_in' in entrance.available_interactions(arena.ally)
    entrance.use(arena.ally, {'action': 'climb_in', 'battle': None}, arena.session)
    assert arena.session.map_for(arena.ally) is zone.pocket_map()


def test_climb_in_refused_when_too_far(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    entrance = zone.entrance()
    # goblin is far away: the use path refuses
    assert entrance.use(arena.goblin, {'action': 'climb_in', 'battle': None}, arena.session) is False
    assert arena.session.map_for(arena.goblin) is arena.map


def test_full_space_blocks_newcomers(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    zone.capacity = 2  # caster + ally already inside
    entrance = zone.entrance()
    details = entrance.available_interactions(arena.goblin)['climb_in']
    assert details.get('disabled')
    assert entrance.use(arena.goblin, {'action': 'climb_in', 'battle': None}, arena.session) is False


def test_pull_rope_up_hides_entrance(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    inner = zone.inner_entrance()
    inner.use(arena.ally, {'action': 'pull_rope'}, arena.session)
    assert zone.rope_stowed
    assert zone.entrance().token_image() is None
    assert zone.entrance().concealed()
    details = zone.entrance().available_interactions(arena.goblin)['climb_in']
    assert details.get('disabled') and 'pulled up' in details.get('disabled_text', '')
    inner.use(arena.ally, {'action': 'drop_rope'}, arena.session)
    assert not zone.rope_stowed
    assert zone.entrance().token_image() == 'objects/rope_trick.png'


def test_rope_square_is_the_dispel_target(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    # clicking the rope square finds the zone...
    covering = zones_at(None, arena.map, (2, 2))
    assert zone in covering
    # ...and so does the rope object itself
    assert zone_for_target(zone.entrance(), None, arena.map) is zone
    end_spell_zone(zone)
    assert zone._dismissed
    assert zone.pocket_map() is None
    assert zone.id not in (arena.session.session_state.get('pocket_dimensions') or {})
    for member in (arena.caster, arena.ally):
        assert arena.session.map_for(member) is arena.map
        assert member.allow_targeting()
        assert not is_restricted(member, 'attack')
        assert not member.has_effect('rope_trick')
    assert [o for o in arena.map.objects_at(2, 2) if getattr(o, 'zone', None)] == []


def test_dismiss_via_spell_ejects_everyone(tmp_path):
    arena, effect, zone = _cast(tmp_path)
    arena.caster.dismiss_effect(effect)
    assert zone._dismissed
    assert zone.pocket_map() is None
    for member in (arena.caster, arena.ally):
        assert arena.session.map_for(member) is arena.map
        assert member.allow_targeting()
        assert not member.has_effect('rope_trick')


def test_expiry_drops_everyone_out(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    from natural20.environment_zones import tick_environment_zones
    arena.session.increment_game_time(3605)
    tick_environment_zones(arena.session.maps, event_manager=arena.session.event_manager)
    assert zone._dismissed
    assert 'pocket' not in ' '.join(arena.session.maps.keys())
    for member in (arena.caster, arena.ally):
        assert arena.session.map_for(member) is arena.map
        assert member.allow_targeting()
        assert not is_restricted(member, 'spell')
        assert not member.has_effect('rope_trick')


def test_save_load_round_trip(tmp_path):
    arena, _effect, zone = _cast(tmp_path)
    dump = arena.serialize_all()
    session2, _battle2, maps2 = arena.deserialize(dump)
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    ally2 = session2.entity_by_uid(arena.ally.entity_uid)
    pocket2 = maps2[zone.pocket_map_name]
    assert session2.map_for(ally2) is pocket2
    assert not ally2.allow_targeting() and not caster2.allow_targeting()
    assert is_restricted(ally2, 'spell')
    zone2 = find_pocket_zone(session2, zone_id=zone.id, battle=None)
    assert zone2 is not None
    assert zone2.map is maps2['field']  # anchored on the outer map
    assert zone2.entrance() is not None and zone2.inner_entrance() is not None
    assert zone2.entrance().zone is zone2
    spell2 = caster2.effects['rope_trick'][0]['effect']
    assert spell2.zone() is zone2
    # climbing out still works after a save/load
    zone2.inner_entrance().use(ally2, {'action': 'climb_out'}, session2)
    assert session2.map_for(ally2) is maps2['field']
    # and dismissing tears the space down again
    caster2.dismiss_effect(spell2)
    assert zone2._dismissed
    assert ally2.allow_targeting() and caster2.allow_targeting()
