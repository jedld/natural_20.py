"""Silence: 20-ft sphere that blocks verbal spells and speech and grants thunder immunity."""
from natural20.spell.objects.silence_tile import SilenceTile
from natural20.spell.silence_spell import SilenceEffect, SilenceZone, has_silence_ward
from natural20.utils.combat_comms import can_hear, speech_block_reason
from natural20.utils.silence import entity_in_silenced_area
from natural20.utils.spell_requirements import environment_issue
from tests.ranger_spell_helpers import Arena

CENTER = [9, 2]  # radius 4 squares: both goblins inside, caster (2, 2) and ally (3, 2) outside


def _cast(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', spells=['silence'])
    arena.cast('silence', 2, CENTER)
    zone = next(z for z in arena.battle.active_zones if isinstance(z, SilenceZone))
    return arena, zone


def test_yaml_definition(tmp_path):
    arena = Arena(tmp_path, spells=['silence'])
    details = arena.spell('silence')
    assert details['spell_class'] == 'Natural20::Silence'
    assert details.get('ritual') and details.get('concentration')
    assert 'ranger' in [c.lower() for c in details['spell_list_classes']]


def test_cast_places_tiles_and_concentration(tmp_path):
    arena, zone = _cast(tmp_path)
    assert isinstance(arena.caster.concentration, SilenceEffect)
    tiles = [o for o in arena.map.interactable_objects if isinstance(o, SilenceTile)]
    assert len(tiles) == len(zone.squares)
    assert entity_in_silenced_area(arena.goblin)
    assert not entity_in_silenced_area(arena.caster)


def test_verbal_spells_blocked_inside_only(tmp_path):
    arena, _zone = _cast(tmp_path)
    fire_bolt = arena.session.load_spell('firebolt')
    assert environment_issue(arena.goblin, fire_bolt, arena.battle) == 'silenced'
    assert environment_issue(arena.caster, fire_bolt, arena.battle) is None


def test_speech_and_hearing_blocked_inside(tmp_path):
    arena, _zone = _cast(tmp_path)
    assert speech_block_reason(arena.goblin) == 'silenced'
    assert not can_hear(arena.goblin)
    assert speech_block_reason(arena.caster) != 'silenced'


def test_thunder_immunity_follows_position(tmp_path):
    arena, _zone = _cast(tmp_path)
    assert has_silence_ward(arena.goblin)
    assert arena.goblin.immune_to('thunder')
    arena.map.move_to(arena.goblin, 2, 8, arena.battle)
    assert not arena.goblin.immune_to('thunder')


def test_dismiss_clears_tiles_and_wards(tmp_path):
    arena, _zone = _cast(tmp_path)
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert not [o for o in arena.map.interactable_objects if isinstance(o, SilenceTile)]
    assert not entity_in_silenced_area(arena.goblin)
    assert not has_silence_ward(arena.goblin)
    assert not arena.goblin.immune_to('thunder')


def test_save_load_round_trip(tmp_path):
    arena, _zone = _cast(tmp_path)
    session2, battle2, maps2 = arena.round_trip()
    goblin2 = session2.entity_by_uid(arena.goblin.entity_uid)
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    assert entity_in_silenced_area(goblin2)
    assert goblin2.immune_to('thunder')
    assert any(isinstance(z, SilenceZone) for z in battle2.active_zones)
    caster2.dismiss_effect(caster2.concentration)
    assert not entity_in_silenced_area(goblin2)
    assert not goblin2.immune_to('thunder')
