"""Gaseous Form: 10 ft fly speed, nonmagical B/P/S resistance, STR/DEX/CON save advantage, no attacks or spells."""
from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.utils.action_restrictions import is_restricted
from natural20.utils.serialization import Serialization
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena


def _misted():
    arena = SpellArena()
    arena.learn(arena.wizard, 'gaseous_form', 3)
    arena.cast(arena.wizard, 'gaseous_form', 3, arena.wizard)
    return arena


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('gaseous_form')
    assert spell_is_implemented('gaseous_form', meta)
    assert meta['concentration'] is True
    assert meta['spell_list_classes'] == ['Sorcerer', 'Warlock', 'Wizard']


def test_form_changes_movement_and_defenses():
    arena = _misted()
    wizard = arena.wizard
    assert wizard.is_flying()
    assert wizard.speed() == 10
    resistances = wizard.effective_resistances()
    for res in ('non-magical bludgeoning', 'non-magical piercing', 'non-magical slashing'):
        assert res in resistances
    adv, _dis = wizard.eval_effect('save_advantage_modifier', {'value': [[], []], 'save_type': 'dexterity'})
    assert 'gaseous_form' in adv
    adv, _dis = wizard.eval_effect('save_advantage_modifier', {'value': [[], []], 'save_type': 'wisdom'})
    assert 'gaseous_form' not in adv


def test_cannot_attack_cast_or_speak():
    arena = _misted()
    wizard = arena.wizard
    wizard.reset_turn(arena.battle)
    assert not AttackAction.can(wizard, arena.battle)
    assert not SpellAction.can_cast(wizard, arena.battle, 'magic_missile')
    assert is_restricted(wizard, 'speak')
    assert is_restricted(wizard, 'interact')


def test_ending_concentration_restores_form():
    arena = _misted()
    wizard = arena.wizard
    wizard.dismiss_effect(wizard.concentration)
    assert not wizard.is_flying()
    assert 'gaseous_form' not in wizard.statuses
    assert not is_restricted(wizard, 'attack')
    assert 'non-magical slashing' not in wizard.effective_resistances()


def test_survives_save_and_load():
    arena = _misted()
    serializer = Serialization()
    _session, battle, _maps = serializer.deserialize(
        serializer.serialize(arena.session, arena.battle, [arena.map]))
    wizard = next(e for e in battle.entities if e.entity_uid == arena.wizard.entity_uid)
    assert is_restricted(wizard, 'attack')
    wizard.dismiss_effect(wizard.concentration)
    assert not is_restricted(wizard, 'attack')
