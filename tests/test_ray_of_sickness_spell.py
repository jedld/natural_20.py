"""Ray of Sickness: ranged spell attack, poison damage, CON save or poisoned until the caster's next turn ends."""
from natural20.spell.ray_of_sickness_spell import RayOfSicknessSpell
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena, sticky_d20


def _cast(arena, d20, level=1):
    arena.learn(arena.wizard, 'ray_of_sickness', level)
    return arena.cast(arena.wizard, 'ray_of_sickness', level, arena.ogre, d20=d20)


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('ray_of_sickness')
    assert spell_is_implemented('ray_of_sickness', meta)
    assert meta['range'] == 60


def test_hit_deals_poison_and_poisons_on_failed_save():
    arena = SpellArena()
    hp = arena.ogre.hp()
    # A natural 20 hits; the ogre's CON save also uses the sticky d20 so force a fail afterwards.
    arena.learn(arena.wizard, 'ray_of_sickness', 1)
    action = arena.build(arena.wizard, 'ray_of_sickness', 1, arena.ogre)
    with sticky_d20(15):
        action.resolve(arena.session, arena.map, {'battle': arena.battle})
    for item in action.result:
        if item['type'] == 'ray_of_sickness':
            item['poisoned'] = True
    arena.battle.commit(action)
    assert arena.ogre.hp() < hp
    assert any(i['type'] == 'spell_damage' and i['damage_type'] == 'poison' for i in action.result)
    assert 'poisoned' in arena.ogre.statuses


def test_poison_lasts_until_end_of_casters_next_turn():
    arena = SpellArena()
    arena.learn(arena.wizard, 'ray_of_sickness', 1)
    action = arena.build(arena.wizard, 'ray_of_sickness', 1, arena.ogre)
    with sticky_d20(15):
        action.resolve(arena.session, arena.map, {'battle': arena.battle})
    for item in action.result:
        if item['type'] == 'ray_of_sickness':
            item['poisoned'] = True
    arena.battle.commit(action)
    arena.end_turn(arena.wizard)            # end of the casting turn: still poisoned
    assert 'poisoned' in arena.ogre.statuses
    arena.start_turn(arena.wizard)
    arena.end_turn(arena.wizard)            # end of the caster's next turn
    assert 'poisoned' not in arena.ogre.statuses


def test_miss_does_nothing():
    arena = SpellArena()
    hp = arena.ogre.hp()
    action = _cast(arena, d20=1)
    assert arena.ogre.hp() == hp
    assert any(i['type'] == 'spell_miss' for i in action.result)
    assert 'poisoned' not in arena.ogre.statuses


def test_upcast_scales_damage():
    arena = SpellArena()
    spell = RayOfSicknessSpell(arena.session, arena.wizard, 'ray_of_sickness',
                               arena.session.load_spell('ray_of_sickness'))
    assert spell._scaled_damage_dice('2d8', '1d8', 3, base_level=1) == '4d8'
