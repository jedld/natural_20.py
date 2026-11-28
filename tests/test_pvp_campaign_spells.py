"""Engine coverage for the content added for the dnd_pvp roster imports:
Freedom of Movement, Conjure Animals (multi-spirit summons), Wall of Thorns,
Frostbite, Regenerate, Wind Walk, Investiture of Flame, plus the Vorpal
beheading helper.
"""
import pytest

from natural20.die_roll import DieRoll
from natural20.spell.freedom_of_movement_spell import FreedomOfMovementEffect
from natural20.utils.vorpal import vorpal_beheading_roll
from tests.ranger_spell_helpers import Arena, forced_save

XGE = ['xanathars_guide']
EE = ['elemental_evolution']


def _fof(arena, target):
    arena.cast('freedom_of_movement', 4, target)
    return target


def test_freedom_of_movement_ignores_difficult_terrain(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='ranger',
                  spells=['freedom_of_movement', 'spike_growth'])
    # Thorns patch centered at (11, 2): path through (7..8, 4) is inside.
    arena.cast('spike_growth', 2, [11, 2])
    path = [(6, 4), (7, 4), (8, 4)]
    caster = arena.caster
    normal_cost = arena.map.movement_cost(caster, path, arena.battle)

    _fof(arena, caster)
    free_cost = arena.map.movement_cost(caster, path, arena.battle)
    assert free_cost.budget > normal_cost.budget


def test_freedom_of_movement_refuses_grapple_and_restraint(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['freedom_of_movement'])
    target = _fof(arena, arena.caster)
    assert target.immune_to_condition('paralyzed')
    assert target.immune_to_condition('restrained')
    assert target.immune_to_condition('grappled')
    assert not target.immune_to_condition('frightened')
    # Dismissal drops the immunities.
    target.remove_effect('freedom_of_movement')
    target.remove_effect('condition_immunity')
    assert not target.immune_to_condition('grappled')


def test_conjure_animals_sums_up_the_spirits(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='ranger',
                  spells=['conjure_animals'])
    arena.cast('conjure_animals', 3, 'cr1', [4, 5])
    spirits = [e for e in arena.battle.entities
               if e.properties.get('summon_name') == 'conjure_animals']
    assert len(spirits) == 2

    arena.cast('conjure_animals', 5, 'cr_quarter', [4, 5])
    spirits = [e for e in arena.battle.entities
               if e.properties.get('summon_name') == 'conjure_animals']
    # 8 beasts at base level, doubled by the 5th-level slot.
    assert len(spirits) == 16
    names = {e.name for e in spirits}
    assert any(n.endswith(' 2') for n in names)


def test_conjure_animals_spirits_vanish_with_the_spell(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='ranger',
                  spells=['conjure_animals'])
    arena.cast('conjure_animals', 3, 'cr1', [4, 5])
    spirits = [e for e in arena.battle.entities
               if e.properties.get('summon_name') == 'conjure_animals']
    assert len(spirits) == 2
    arena.caster.remove_effect('conjure_animals')
    remaining = [e for e in arena.battle.entities
                 if e.properties.get('summon_name') == 'conjure_animals']
    assert remaining == []


def test_wall_of_thorns_places_wall_and_blocks_los(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    arena.cast('wall_of_thorns', 6, 'wall', [8, 8])
    zone = next(z for z in arena.battle.active_zones if z.name == 'wall_of_thorns')
    tiles = [o for o in arena.map.interactable_objects if o.properties.get('wall_of_thorns')]
    assert len(tiles) == 12  # 60 ft wall on a 5 ft grid
    assert all(t.properties.get('opaque') for t in tiles)
    # The wall blocks line of sight through its squares.
    assert not arena.map.line_of_sight(6, 6, 6, 10)
    # Very costly to move through (4 squares of movement per square).
    assert all(t.properties.get('movement_cost') == 4 for t in tiles)
    assert arena.map.difficult_terrain(arena.goblin2, 8, 8, arena.battle)
    # Entering the wall forces a Dex save; a failed save takes damage.
    goblin = arena.goblin
    arena.map.move_to(goblin, 8, 8, arena.battle)
    before = goblin.hp()
    with forced_save(goblin, 1):
        zone.on_enter(goblin)
    assert goblin.hp() < before
    # ... but entering twice on the same turn only burns once.
    hp_after = goblin.hp()
    with forced_save(goblin, 1):
        zone.on_enter(goblin)
    assert goblin.hp() == hp_after
    zone.dismiss()
    assert not [o for o in arena.map.interactable_objects
                if o.properties.get('wall_of_thorns')]


def test_wall_of_thorns_circle_and_upcast(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    arena.cast('wall_of_thorns', 7, 'circle', [8, 8])
    zone = next(z for z in arena.battle.active_zones if z.name == 'wall_of_thorns')
    # 20 ft diameter ring: the 12 squares on a 4x4 block centered on (8, 8)
    # (outer 20 ft, inner 10 ft hole).
    assert len(zone._square_set) == 12
    assert (6, 6) in zone._square_set and (9, 9) in zone._square_set
    assert (6, 8) in zone._square_set
    assert (8, 8) not in zone._square_set and (7, 7) not in zone._square_set
    # Slot 7 (one above 6th): both damage dice gain 1d8.
    assert zone.appearance_dice == '8d8'
    assert zone.enter_dice == '8d8'
    # Ending a turn inside the wall hurts too (once).
    goblin = arena.goblin
    arena.map.move_to(goblin, 6, 6, arena.battle)
    before = goblin.hp()
    with forced_save(goblin, 1):
        zone.on_turn_end(goblin)
    assert goblin.hp() < before


def test_frostbite_damage_blocks_reactions(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', packs=XGE, caster='wizard',
                  spells=['frostbite'])
    goblin = arena.goblin
    with pytest.MonkeyPatch.context() as mp:
        goblin.save_throw = lambda *a, **k: DieRoll.roll('1')
        arena.cast('frostbite', 0, goblin)
    assert goblin.hp() < goblin.properties['max_hp']
    assert 'frostbitten' in goblin.statuses


def test_regenerate_heals_at_start_of_turn(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['regenerate'])
    target = arena.ally
    target.set_hp(10)
    arena.cast('regenerate', 7, target)
    DieRoll.fudge(4)
    from natural20.battle import Battle  # noqa: F401  (hook dispatch path)
    amount = None
    for hook in target.entity_event_hooks.get('start_of_turn', []):
        if hook['handler'].__name__ == 'RegenerateEffect':
            amount = hook['handler'].start_of_turn(target, {'effect': hook['effect']})
    assert amount and amount > 0
    assert target.hp() > 10


def test_wind_walk_grants_mist_form_speed(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wind_walk'])
    target = arena.ally
    arena.cast('wind_walk', 6, [target])
    assert 'gaseous_form' in target.statuses
    assert target.eval_effect('speed_override', {'stacked': True, 'value': 30}) == 300


def test_investiture_of_flame_aura_and_line(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', packs=EE, caster='druid',
                  spells=['investiture_of_flame'], slot_class='druid')
    caster = arena.caster
    arena.cast('investiture_of_flame', 6, caster)
    assert 'investiture_of_flame' in caster.statuses
    assert 'fire' in caster.eval_effect('immunity_override',
                                        {'stacked': True, 'value': []})
    assert 'cold' in caster.eval_effect('resistance_override',
                                        {'stacked': True, 'value': []})
    zone = next(z for z in arena.battle.active_zones
                if type(z).__name__ == 'InvestitureFlameAuraZone')
    goblin = arena.goblin
    arena.map.move_to(goblin, 4, 2, arena.battle)
    goblin.set_hp(30, override_max=True)
    before = goblin.hp()
    zone.strike(goblin, reason='turn_start')
    assert goblin.hp() < before

    from natural20.actions.flame_line_action import FlameLineAction
    assert FlameLineAction.can(caster, arena.battle)
    line = FlameLineAction(arena.session, caster, 'investiture_flame_line')
    line.target = [8, 2]
    DieRoll.fudge(20)
    line.resolve(arena.session, arena.map, {'battle': arena.battle})
    assert any(r['type'] == 'flame_line_damage' for r in line.result)


def test_vorpal_beheading_roll(tmp_path):
    arena = Arena(tmp_path, with_battle=False)
    goblin = arena.goblin

    class _W:
        pass

    roll = vorpal_beheading_roll(arena.caster, goblin, {}, arena.battle)
    assert roll is not None and roll.expected() > goblin.hp()

    goblin.damage_immunities = ['slashing']
    roll = vorpal_beheading_roll(arena.caster, goblin, {}, arena.battle)
    assert roll is not None and roll.expected() == 30
