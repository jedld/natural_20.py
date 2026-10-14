"""Sanctuary: attackers save (WIS) or lose the attack/spell; ward ends when the warded creature attacks."""
from natural20.actions.attack_action import AttackAction
from natural20.spell.sanctuary_spell import SanctuaryEffect
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena, sticky_d20


def _warded():
    arena = SpellArena()
    arena.learn(arena.cleric, 'sanctuary', 1)
    arena.cast(arena.cleric, 'sanctuary', 1, arena.wizard)
    return arena


def _ogre_attacks(arena, target):
    arena.ogre.reset_turn(arena.battle)
    arena.map.move_to(arena.ogre, 1, 5, arena.battle)
    action = AttackAction(arena.session, arena.ogre, 'attack')
    action.target = target
    action.npc_action = arena.ogre.npc_actions[0]
    action.using = action.npc_action['name']
    arena.battle.execute_action(action)
    return action


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('sanctuary')
    assert spell_is_implemented('sanctuary', meta)
    assert meta['casting_time'] == '1:bonus_action'


def test_registers_ward():
    arena = _warded()
    assert arena.wizard.has_effect('targeting_ward')
    ward = arena.wizard.eval_effect('targeting_ward', {'attacker': arena.ogre})
    assert ward['save_type'] == 'wisdom'
    assert ward['dc'] == arena.cleric.spell_save_dc('wisdom')


def test_failed_save_loses_attack():
    arena = _warded()
    hp = arena.wizard.hp()
    with sticky_d20(1):
        action = _ogre_attacks(arena, arena.wizard)
    ward_items = [i for i in action.result if i['type'] == 'targeting_ward']
    assert ward_items and ward_items[0]['blocked']
    assert not any(i['type'] in ('damage', 'miss') for i in action.result)
    assert arena.wizard.hp() == hp


def test_successful_save_lets_attack_through():
    arena = _warded()
    with sticky_d20(20):
        action = _ogre_attacks(arena, arena.wizard)
    ward_items = [i for i in action.result if i['type'] == 'targeting_ward']
    assert ward_items and not ward_items[0]['blocked']
    assert any(i['type'] == 'damage' for i in action.result)


def test_harmful_spell_is_lost_on_failed_save():
    arena = _warded()
    arena.battle.add(arena.session.npc('goblin'), 'foes', position=[6, 6])
    caster = arena.wizard
    # The cleric shields the wizard; an enemy wizard (the cleric switched sides) casts at them.
    arena.battle.entities[arena.cleric]['group'] = 'foes'
    arena.learn(arena.cleric, 'guiding_bolt', 1)
    hp = caster.hp()
    with sticky_d20(1):
        action = arena.cast(arena.cleric, 'guiding_bolt', 1, caster)
    assert any(i['type'] == 'targeting_ward' and i['blocked'] for i in action.result)
    assert caster.hp() == hp


def test_ward_ends_when_warded_creature_attacks():
    arena = _warded()
    effect = next(d['effect'] for d in arena.wizard.effects['targeting_ward'])
    assert isinstance(effect, SanctuaryEffect)
    arena.wizard.resolve_trigger('attack_resolved', {'battle': arena.battle})
    assert not arena.wizard.has_effect('targeting_ward')


def test_ward_ends_when_warded_creature_deals_damage():
    arena = _warded()
    arena.learn(arena.wizard, 'magic_missile', 1)
    arena.cast(arena.wizard, 'magic_missile', 1, [arena.ogre, arena.ogre, arena.ogre])
    assert not arena.wizard.has_effect('targeting_ward')
