"""Item coverage for the dnd_pvp imports: luckstone bonuses, pearl of power,
oil of slipperiness, the Deck of Many Things draw model and the Mirror of
Reflected Pasts gaze."""
from natural20.actions.use_item_action import UseItemAction
from natural20.item_library.deck_of_many_things import (
    CARDS, FULL_DECK_ONLY, DeckOfManyThingsItem, _draw_pool)
from natural20.item_library.pearl_of_power import PearlOfPowerItem
from natural20.utils.item_mechanics import item_ability_check_bonus, item_save_bonus
from tests.ranger_spell_helpers import Arena


def _use_item(arena, user, item_key, target=None, draws=1):
    action = UseItemAction(arena.session, user, f'use_item:{item_key}')
    action.target_item = None
    step = action.build_next(item_key)
    if isinstance(step, dict):
        param = (step.get('param') or [{}])[0]
        if param.get('type') == 'select_choice':
            step = step['next'](draws)
        elif callable(step.get('next')):
            step = step['next'](target or user)
    if isinstance(step, UseItemAction):
        action = step
    action.target = target or user
    action.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(action)
    return action


def test_luckstone_grants_save_and_check_bonuses(tmp_path):
    arena = Arena(tmp_path, with_battle=False)
    pc = arena.caster
    pc.add_item('stone_of_good_luck_luckstone', 1)
    pc.properties.setdefault('equipped', []).append('stone_of_good_luck_luckstone')
    assert item_save_bonus(pc) == 1
    assert item_ability_check_bonus(pc) == 1
    pc.properties['equipped'] = []
    assert item_save_bonus(pc) == 0


def test_pearl_of_power_restores_a_slot(tmp_path):
    arena = Arena(tmp_path, caster='wizard')
    wizard = arena.caster
    wizard.add_item('pearl_of_power', 1)
    maximum = wizard.max_spell_slots(1, 'wizard')
    wizard.spell_slots['wizard'][1] = maximum - 1
    _use_item(arena, wizard, 'pearl_of_power')
    assert wizard.spell_slots['wizard'][1] == maximum
    # Once per dawn: the second use is refused.
    _use_item(arena, wizard, 'pearl_of_power')
    assert wizard.spell_slots['wizard'][1] == maximum


def test_pearl_downgrades_higher_slot_to_third(tmp_path):
    slots = {'wizard': {3: 0, 4: 0}}

    class _PC:
        spell_slots = slots

        @staticmethod
        def max_spell_slots(level, klass):
            return {3: 2, 4: 1}[level]

    restored = PearlOfPowerItem._restore_slot(_PC())
    assert restored and slots['wizard'][3] == 1 and slots['wizard'][4] == 0


def test_oil_of_slipperiness_gives_freedom_of_movement(tmp_path):
    arena = Arena(tmp_path, caster='ranger')
    pc = arena.caster
    pc.add_item('oil_of_slipperiness', 1)
    assert not pc.immune_to_condition('restrained')
    _use_item(arena, pc, 'oil_of_slipperiness', target=pc)
    assert pc.immune_to_condition('restrained')
    assert pc.immune_to_condition('paralyzed')
    assert pc.has_effect('freedom_of_movement')


def test_deck_draw_pool_and_fade(tmp_path):
    pool13 = _draw_pool(13)
    full = _draw_pool(22)
    assert len(full) == len(CARDS) == 22
    assert set(pool13) == set(full) - FULL_DECK_ONLY
    assert FULL_DECK_ONLY <= set(full)

    arena = Arena(tmp_path)
    pc = arena.caster
    pc.add_item('deck_of_many_things', 1)
    _use_item(arena, pc, 'deck_of_many_things', draws=3)
    entry = pc.inventory.get('deck_of_many_things') or {}
    history = entry.get('deck_drawn') or []
    assert len(history) == 3
    assert len(set(history)) == 3
    assert all(card in full for card in history)


def test_mirror_gaze_paralyzes_and_grants_immunity(tmp_path):
    arena = Arena(tmp_path, packs=['wildemount'])
    pc = arena.caster
    pc.add_item('mirror_of_reflected_pasts', 1)
    _use_item(arena, pc, 'mirror_of_reflected_pasts', target=pc)
    assert pc.has_effect('mirror_gaze')

    from natural20.item_library.mirror_ward import MirrorGazeEffect
    effect = next(d['effect'] for d in pc.effects['mirror_gaze'])
    assert isinstance(effect, MirrorGazeEffect)
    goblin = arena.goblin
    # Force the save to fail and gaze the goblin.
    from natural20.die_roll import DieRoll
    goblin.save_throw = lambda *a, **k: DieRoll.roll('1')
    effect.on_owner_turn(pc, {'battle': arena.battle})
    assert 'paralyzed' in goblin.statuses
    # Repeated Wisdom save at the end of its turn (forced success).
    goblin.save_throw = lambda *a, **k: DieRoll.roll('30')
    effect.on_target_end_of_turn(goblin, {'battle': arena.battle})
    assert 'paralyzed' not in goblin.statuses
    until = goblin.properties.get('mirror_gaze_immune_until')
    assert until and arena.session.game_time < until
    # Second sight no longer targets it.
    visible = [e for e, *_ in effect._visible_targets(battle=arena.battle)]
    assert goblin not in visible

    # Deactivate: effect removed.
    _use_item(arena, pc, 'mirror_of_reflected_pasts', target=pc)
    assert not pc.has_effect('mirror_gaze')
