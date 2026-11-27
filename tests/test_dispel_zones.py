"""Dispel Magic on persistent spell zones (SRD "magical effect" targeting).

The caster may aim at any square a zone covers (coordinates), and when
several zones overlap the square ``opts.effect_id`` picks which one.
"""
from natural20.die_roll import DieRoll
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.objects.spike_growth_tile import SpikeGrowthTile
from natural20.spell.spike_growth_spell import SpikeGrowthZone
from natural20.spell.wizard_spells import DispelMagicSpell
from natural20.utils.dispel import (
    end_spell_zone,
    zone_for_target,
    zone_label,
    zone_spell_level,
    zones_at,
)
from tests.ranger_spell_helpers import Arena

CENTER = [11, 2]


def _cast_spike_growth(arena, level=2):
    arena.cast('spike_growth', level, CENTER)
    return next(z for z in arena.battle.active_zones if isinstance(z, SpikeGrowthZone))


def _tiles(arena):
    return [o for o in arena.map.interactable_objects if isinstance(o, SpikeGrowthTile)]


def test_zone_lookup_by_square_and_effect_id(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='wizard',
                  spells=['spike_growth', 'dispel_magic'])
    zone = _cast_spike_growth(arena)

    assert zones_at(arena.battle, arena.map, CENTER) == [zone]
    assert zone_for_target(CENTER, arena.battle, arena.map) is zone
    assert zone_for_target([11, 99], arena.battle, arena.map) is None
    assert zone_label(zone) == 'Spike Growth'
    assert zone_spell_level(zone) == 2


def test_dispel_coordinate_target_ends_zone(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='wizard',
                  spells=['spike_growth', 'dispel_magic'])
    zone = _cast_spike_growth(arena)
    assert _tiles(arena)

    events = []
    arena.session.event_manager.register_event_listener(
        'dispel_magic', lambda event: events.append(event))

    action = arena.cast('dispel_magic', 3, CENTER)
    assert zone._dismissed
    assert _tiles(arena) == []
    assert arena.caster.concentration is None
    assert events and events[0].get('zone_label') == 'Spike Growth'
    assert events[0]['outcomes'][0]['ended'] is True


def test_higher_level_zone_forces_a_check(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='wizard',
                  spells=['spike_growth', 'dispel_magic'])
    zone = _cast_spike_growth(arena, level=4)
    assert zone_spell_level(zone) == 4

    # Fail the spellcasting check (1 + 4 mod < DC 14): the zone holds.
    original = DispelMagicSpell._dispel_check
    DispelMagicSpell._dispel_check = lambda self, e, b, sa: DieRoll.roll('1')
    try:
        arena.cast('dispel_magic', 3, CENTER)
    finally:
        DispelMagicSpell._dispel_check = original
    assert not zone._dismissed
    assert arena.caster.concentration is not None

    # Succeed (20 >= 14) and the zone ends.
    DispelMagicSpell._dispel_check = lambda self, e, b, sa: DieRoll.roll('20')
    try:
        arena.cast('dispel_magic', 3, CENTER)
    finally:
        DispelMagicSpell._dispel_check = original
    assert zone._dismissed
    assert _tiles(arena) == []


def test_overlapping_zones_effect_id_picks(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='wizard',
                  spells=['spike_growth', 'dispel_magic'])
    spike = _cast_spike_growth(arena)

    # A second magical effect covering the same square (plain zone).
    other = PersistentAoEZone(arena.caster, arena.battle, arena.map,
                              [(11, 2), (12, 2)], name='web')
    arena.battle.register_zone(other)

    covering = zones_at(arena.battle, arena.map, CENTER)
    assert set(covering) == {spike, other}

    # Mirrors the web route: the picker's choice is carried on the built
    # SpellAction as effect_id before resolve/commit.
    action = arena.build('dispel_magic', 3, CENTER)
    action.effect_id = other.id
    action.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(action)

    assert other._dismissed
    assert not spike._dismissed
    assert _tiles(arena), 'the Spike Growth field must survive'
    # Concentration stays on the Spike Growth effect (its owner-side hook).
    assert arena.caster.concentration is not None
    assert arena.caster.concentration.zone is spike


def test_end_spell_zone_falls_back_to_force_dismiss(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='wizard',
                  spells=['spike_growth', 'dispel_magic'])
    zone = _cast_spike_growth(arena)
    # A zone with no owner-side effect entry (e.g. a hazard-style zone).
    lone = PersistentAoEZone(None, arena.battle, arena.map, [(11, 2)], name='grease')
    arena.battle.register_zone(lone)
    assert end_spell_zone(lone) is True
    assert lone._dismissed
    assert not zone._dismissed
