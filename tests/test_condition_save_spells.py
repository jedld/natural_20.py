"""YAML-driven condition spells (natural20/spell/condition_spells.py) and the
off-plane helper: Hold Monster, Hypnotic Pattern, Dominate Person/Beast,
Banishment, Calm Emotions and Phantasmal Force."""
from natural20.actions.spell_action import SpellAction
from natural20.npc import Npc
from natural20.spell.condition_spells import ConditionSaveSpell, ConditionSpellEffect
from natural20.utils.action_builder import acquire_targets
from natural20.utils.action_restrictions import is_restricted
from natural20.utils.off_plane import off_plane
from natural20.utils.spell_loader import load_spell_class
from tests.ranger_spell_helpers import Arena, forced_save

SPELLS = ['hold_monster', 'hypnotic_pattern', 'dominate_person', 'dominate_beast', 'banishment',
          'calm_emotions', 'phantasmal_force']


def _arena(tmp_path, ruleset='5e-2014'):
    return Arena(tmp_path, ruleset=ruleset, caster='wizard', spells=SPELLS)


def _effect(entity):
    for entry in entity.effects.get('condition_spell', []):
        if isinstance(entry.get('effect'), ConditionSpellEffect):
            return entry['effect']
    return None


def test_spell_classes_registered():
    for key in ('HoldMonsterSpell', 'HypnoticPatternSpell', 'DominatePersonSpell', 'DominateBeastSpell',
                'BanishmentSpell', 'CalmEmotionsSpell', 'PhantasmalForceSpell'):
        assert load_spell_class(key) is ConditionSaveSpell


def test_hold_monster_paralyzes_until_end_of_turn_save(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin, 1):
        arena.cast('hold_monster', 5, [arena.goblin])
    assert 'paralyzed' in arena.goblin.statuses
    assert arena.caster.concentration is not None
    with forced_save(arena.goblin, 1):
        arena.goblin.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert 'paralyzed' in arena.goblin.statuses
    with forced_save(arena.goblin, 30):
        arena.goblin.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert 'paralyzed' not in arena.goblin.statuses
    assert arena.caster.concentration is None


def test_hold_monster_upcast_targets_two(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin, 1), forced_save(arena.goblin2, 1):
        arena.cast('hold_monster', 6, [arena.goblin, arena.goblin2])
    assert 'paralyzed' in arena.goblin.statuses and 'paralyzed' in arena.goblin2.statuses


def test_hold_monster_targeting_excludes_undead(tmp_path):
    arena = _arena(tmp_path)
    step = SpellAction.build(arena.session, arena.caster)['next'](['hold_monster', 5])
    param = step['param'][0]
    assert param.get('exclude_races') == ['undead']
    undead = Npc(arena.session, 'skeleton', {'name': 'skeleton', 'race': ['undead']})
    arena.session.register_entity(undead)
    arena.map.add(undead, 6, 2, 'b')
    arena.battle.add(undead, 'b', add_to_initiative=True)
    assert undead not in acquire_targets(param, arena.caster, arena.battle, arena.map)
    assert arena.goblin in acquire_targets(param, arena.caster, arena.battle, arena.map)


def test_hypnotic_pattern_area_ends_on_damage(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin, 1), forced_save(arena.goblin2, 1):
        arena.cast('hypnotic_pattern', 3, [6, 1])
    for goblin in (arena.goblin, arena.goblin2):
        assert {'charmed', 'incapacitated'} <= set(goblin.statuses)
        assert goblin.speed() == 0
    arena.goblin.take_damage(1, battle=arena.battle, damage_type='fire')
    assert 'incapacitated' not in arena.goblin.statuses
    assert 'incapacitated' in arena.goblin2.statuses


def test_dominate_person_switches_side_and_restores(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin, 1):
        arena.cast('dominate_person', 5, [arena.goblin])
    assert arena.battle.entities[arena.goblin]['group'] == 'a'
    assert not arena.battle.opposing(arena.caster, arena.goblin)
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert arena.battle.entities[arena.goblin]['group'] == 'b'
    assert 'charmed' not in arena.goblin.statuses


def test_dominate_beast_ignores_humanoids(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin, 1):
        action = arena.cast('dominate_beast', 4, [arena.goblin])
    assert any(r.get('message') == 'unaffected' for r in action.result)
    assert arena.battle.entities[arena.goblin]['group'] == 'b'


def test_dominate_beast_repeats_save_on_damage(tmp_path):
    arena = _arena(tmp_path)
    wolf = Npc(arena.session, 'wolf', {'name': 'wolf'})
    arena.session.register_entity(wolf)
    arena.map.add(wolf, 5, 4, 'b')
    arena.battle.add(wolf, 'b', add_to_initiative=True)
    with forced_save(wolf, 1):
        arena.cast('dominate_beast', 4, [wolf])
    assert arena.battle.entities[wolf]['group'] == 'a'
    with forced_save(wolf, 30):
        wolf.take_damage(1, battle=arena.battle, damage_type='fire')
    assert arena.battle.entities[wolf]['group'] == 'b'


def test_banishment_sends_target_off_plane(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin, 1):
        arena.cast('banishment', 4, [arena.goblin])
    assert off_plane(arena.goblin)
    assert not arena.goblin.allow_targeting()
    assert {'banished', 'incapacitated'} <= set(arena.goblin.statuses)
    assert arena.goblin not in arena.map.entities_at(6, 2)
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert not off_plane(arena.goblin)
    assert arena.goblin.allow_targeting()
    assert 'banished' not in arena.goblin.statuses


def test_calm_emotions_wards_allies_and_pacifies_enemies(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin, 1), forced_save(arena.goblin2, 1):
        arena.cast('calm_emotions', 2, [5, 2])
    assert arena.ally.immune_to_condition('charmed')
    assert arena.ally.immune_to_condition('frightened')
    assert is_restricted(arena.goblin, 'attack')
    arena.goblin.take_damage(1, battle=arena.battle, damage_type='fire')
    assert not is_restricted(arena.goblin, 'attack')
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert not arena.ally.immune_to_condition('charmed')


def test_phantasmal_force_damages_each_caster_turn(tmp_path):
    arena = _arena(tmp_path, ruleset='5e-2024')
    assert arena.spell('phantasmal_force')['condition_save']['per_turn_damage']['dice'] == '2d8'
    with forced_save(arena.goblin, 1):
        arena.cast('phantasmal_force', 2, [arena.goblin])
    before = arena.goblin.hp()
    arena.caster.resolve_trigger('start_of_turn', {'battle': arena.battle})
    assert arena.goblin.hp() < before or arena.goblin.dead()


def test_condition_effect_survives_save_load(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin, 1):
        arena.cast('hold_monster', 5, [arena.goblin])
    session2, battle2, _maps = arena.round_trip()
    goblin2 = session2.entity_by_uid(arena.goblin.entity_uid)
    assert 'paralyzed' in goblin2.statuses
    effect = _effect(goblin2)
    assert effect is not None and effect.target_uids == [goblin2.entity_uid]
