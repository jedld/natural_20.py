"""Pass without Trace: +10 Stealth for the caster and nearby allies while within 30 ft."""
from natural20.die_roll import DieRoll
from natural20.spell.pass_without_trace_spell import PassWithoutTraceSpell
from tests.ranger_spell_helpers import Arena


def _stealth(entity, battle):
    DieRoll.fudge(10)
    try:
        return entity.stealth_check(battle).result()
    finally:
        DieRoll.unfudge()


def test_yaml_definition(tmp_path):
    arena = Arena(tmp_path, spells=['pass_without_trace'])
    details = arena.spell('pass_without_trace')
    assert details['spell_class'] == 'Natural20::PassWithoutTrace'
    assert details['concentration'] and details['ai_in_combat'] is False


def test_caster_and_allies_gain_ten_stealth(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', spells=['pass_without_trace'])
    caster_before = _stealth(arena.caster, arena.battle)
    ally_before = _stealth(arena.ally, arena.battle)
    goblin_before = _stealth(arena.goblin, arena.battle)
    arena.cast('pass_without_trace', 2)
    assert isinstance(arena.caster.concentration, PassWithoutTraceSpell)
    assert _stealth(arena.caster, arena.battle) == caster_before + 10
    assert _stealth(arena.ally, arena.battle) == ally_before + 10
    assert _stealth(arena.goblin, arena.battle) == goblin_before


def test_bonus_only_for_stealth(tmp_path):
    arena = Arena(tmp_path, spells=['pass_without_trace'])
    DieRoll.fudge(10)
    before = arena.caster.perception_check(arena.battle).result()
    DieRoll.unfudge()
    arena.cast('pass_without_trace', 2)
    DieRoll.fudge(10)
    after = arena.caster.perception_check(arena.battle).result()
    DieRoll.unfudge()
    assert after == before


def test_ally_leaving_the_aura_loses_bonus(tmp_path):
    arena = Arena(tmp_path, spells=['pass_without_trace'])
    before = _stealth(arena.ally, arena.battle)
    arena.cast('pass_without_trace', 2)
    arena.map.move_to(arena.ally, 2, 12, arena.battle)  # 50 ft away
    assert _stealth(arena.ally, arena.battle) == before


def test_dismiss_removes_bonus(tmp_path):
    arena = Arena(tmp_path, spells=['pass_without_trace'])
    before = _stealth(arena.ally, arena.battle)
    arena.cast('pass_without_trace', 2)
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert _stealth(arena.ally, arena.battle) == before
    assert not arena.ally.has_effect('skill_check_bonus')


def test_save_load_round_trip(tmp_path):
    arena = Arena(tmp_path, spells=['pass_without_trace'])
    before = _stealth(arena.ally, arena.battle)
    arena.cast('pass_without_trace', 2)
    session2, battle2, _maps2 = arena.round_trip()
    ally2 = session2.entity_by_uid(arena.ally.entity_uid)
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    assert _stealth(ally2, battle2) == before + 10
    caster2.dismiss_effect(caster2.concentration)
    assert _stealth(ally2, battle2) == before
