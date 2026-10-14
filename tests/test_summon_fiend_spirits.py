"""Summon Fiend (PHB 2024) spirits: yugoloth teleport, vanishing at 0 HP and
the demon's Death Throes when the spell ends."""
from natural20.actions.attack_action import AttackAction
from natural20.actions.post_attack_teleport_action import PostAttackTeleportAction, WINDOW_KEY
from natural20.die_roll import DieRoll
from natural20.utils.class_mechanics import devils_sight_range
from tests.ranger_spell_helpers import Arena

PACK = ['summon_fiend']


def _summon(tmp_path, variant, at=(2, 5), level=6):
    arena = Arena(tmp_path, ruleset='5e-2024', packs=['players_handbook_2024'], caster='wizard',
                  spells=PACK)
    arena.caster.spell_slots['wizard'][level] = 1
    arena.cast('summon_fiend', level, variant, list(at))
    spirit = next(e for e in arena.battle.entities if e.properties.get('summon_name') == 'summon_fiend')
    arena.battle.current_turn_index = arena.battle.combat_order.index(spirit)
    spirit.reset_turn(arena.battle)
    return arena, spirit


def _claw(arena, spirit, target, d20=15):
    action = AttackAction(arena.session, spirit, 'attack')
    action.npc_action = next(a for a in spirit.npc_actions if a['name'] == 'claws')
    action.target = target
    DieRoll.fudge(d20)
    arena.battle.action(action)
    arena.battle.commit(action)
    return action


def _teleports(arena, spirit, auto_target=True):
    return [a for a in spirit.available_actions(arena.session, arena.battle, auto_target=auto_target)
            if a.action_type == 'post_attack_teleport']


def test_yugoloth_claws_open_a_teleport_window(tmp_path):
    arena, spirit = _summon(tmp_path, 'yugoloth')
    arena.map.move_to(arena.goblin, 4, 5, arena.battle)
    assert not PostAttackTeleportAction.can(spirit, arena.battle)

    action = _claw(arena, spirit, arena.goblin, d20=1)
    assert any(r['type'] == 'post_attack_teleport_window' for r in action.result)
    assert arena.battle.entity_state_for(spirit)[WINDOW_KEY] == 30
    assert PostAttackTeleportAction.can(spirit, arena.battle)

    teleport = PostAttackTeleportAction(arena.session, spirit, 'post_attack_teleport', {'range': 30})
    teleport.target = [8, 8]
    arena.battle.action(teleport)
    arena.battle.commit(teleport)
    assert arena.map.entity_or_object_pos(spirit) == [8, 8]
    assert arena.battle.entity_state_for(spirit)[WINDOW_KEY] == 0
    assert not PostAttackTeleportAction.can(spirit, arena.battle)


def test_teleport_window_closes_at_next_turn_and_rejects_far_squares(tmp_path):
    arena, spirit = _summon(tmp_path, 'yugoloth')
    arena.map.move_to(arena.goblin, 4, 5, arena.battle)
    _claw(arena, spirit, arena.goblin)

    too_far = PostAttackTeleportAction(arena.session, spirit, 'post_attack_teleport', {'range': 30})
    too_far.target = [2, 13]
    too_far.resolve(arena.session, arena.map, {'battle': arena.battle})
    assert not any(r['type'] == 'post_attack_teleport' for r in too_far.result)

    spirit.reset_turn(arena.battle)
    assert not PostAttackTeleportAction.can(spirit, arena.battle)


def test_ai_teleport_options_close_in_while_attacks_remain(tmp_path):
    arena, spirit = _summon(tmp_path, 'yugoloth')
    arena.map.move_to(arena.goblin, 4, 5, arena.battle)
    _claw(arena, spirit, arena.goblin, d20=1)
    arena.map.move_to(arena.goblin, 9, 9, arena.battle)
    arena.map.move_to(arena.goblin2, 10, 9, arena.battle)

    options = _teleports(arena, spirit)
    assert options and len(options) <= 3
    for option in options:
        assert option.target is not None
        assert option.ai_value(arena.battle) > 0
    assert _teleports(arena, spirit, auto_target=False)


def test_spirit_at_zero_hp_vanishes_and_ends_concentration(tmp_path):
    arena, spirit = _summon(tmp_path, 'devil')
    assert arena.caster.concentration is not None
    spirit.take_damage(500, battle=arena.battle)
    assert spirit not in arena.battle.entities
    assert arena.map.entity_or_object_pos(spirit) is None
    assert arena.caster.concentration is None


def test_demon_explodes_when_the_spell_ends(tmp_path):
    arena, spirit = _summon(tmp_path, 'demon', at=(4, 2))
    before = {e: e.hp() for e in (arena.ally, arena.goblin)}
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert spirit not in arena.battle.entities
    assert any(e.hp() < before[e] or e.dead() for e in before)


def test_devil_has_devils_sight_and_mixed_multiattack(tmp_path):
    arena, spirit = _summon(tmp_path, 'devil', level=8)
    assert devils_sight_range(spirit) == 60
    combo = spirit.properties['multiattack']
    assert len(combo) == 1 and combo[0]['count'] == 4
    assert set(combo[0]['any_of']) == {'fiery_strike', 'hurl_flame'}


def test_flat_damage_event_logs_without_a_roll(tmp_path):
    """Retaliation damage (Beguiling Defenses) is a plain int, not a DieRoll."""
    from natural20.utils.attack_util import damage_event
    from natural20.utils.reaction_casts import retaliate
    arena = Arena(tmp_path, caster='wizard')
    arena.session.event_manager.standard_cli()
    hp = arena.goblin.hp()
    damage_event({'source': arena.caster, 'target': arena.goblin, 'damage': 3,
                  'damage_type': 'psychic', 'attack_name': 'retaliation'}, arena.battle)
    assert arena.goblin.hp() == hp - 3

    marker = {'retaliate': {'save': 'wisdom', 'damage_type': 'psychic'}, 'dc': 30, 'label': 'Beguiling'}
    retaliate(marker, arena.caster, arena.goblin2, 2, arena.battle)
    assert arena.goblin2.hp() < arena.goblin2.max_hp() or arena.goblin2.dead()
