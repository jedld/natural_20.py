"""Cross-floor spell and attack targeting across map stacks."""

import pytest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.map_stack_targeting import (
    entity_at_stack_position,
    stack_entity_distance_ft,
    things_at_stack_position,
)
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.action_builder import acquire_targets


@pytest.fixture
def stack_session():
    return Session(root_path='user_levels/wild_sheep_chase')


def test_entity_at_stack_position_resolves_base_map_npc(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    npc = session.npc('skeleton')
    base.add(npc, 13, 15, group='b')

    entity, target_map, lx, ly = entity_at_stack_position(stack, upstairs, 13, 15)
    assert entity is npc
    assert target_map is base
    assert (lx, ly) == (13, 15)


def test_things_at_stack_position_includes_other_floors(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    npc = session.npc('skeleton')
    base.add(npc, 13, 15, group='b')

    hits = things_at_stack_position(stack, 13, 15)
    uids = {getattr(h[3], 'entity_uid', None) for h in hits}
    assert npc.entity_uid in uids


def test_stack_entity_distance_uses_world_space(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    caster = session.npc('goblin')
    target = session.npc('skeleton')
    upstairs.add(caster, 4, 0, group='a')
    base.add(target, 13, 15, group='b')

    dist_ft = stack_entity_distance_ft(
        stack, caster, upstairs, target, base, feet_per_grid=base.feet_per_grid,
    )
    assert dist_ft == 5.0


def test_valid_targets_for_cross_floor_spell_attack(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    from natural20.event_manager import EventManager
    fixture = Session(root_path='tests/fixtures', event_manager=EventManager())
    caster = PlayerCharacter.load(fixture, 'high_elf_mage.yml')
    target = session.npc('skeleton')
    upstairs.add(caster, 4, 0, group='a')
    base.add(target, 13, 15, group='b')

    battle = Battle(session, upstairs)
    battle.add(caster, 'a')
    battle.add(target, 'b')
    battle.start()

    build = SpellAction.build(session, caster)['next'](['firebolt', 0])
    param = build['param'][0]
    acquired = acquire_targets(param, caster, battle, upstairs)
    assert target in acquired

    action = build['next'](target)
    valid = battle.valid_targets_for(caster, action)
    assert target in valid


def test_valid_targets_for_base_attacker_upstairs_target(stack_session):
    """Ground-floor enemies can target upstairs PCs when stack LOS and range allow."""
    from natural20.actions.attack_action import AttackAction
    from natural20.event_manager import EventManager

    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    fixture = Session(root_path='tests/fixtures', event_manager=EventManager())
    target_pc = PlayerCharacter.load(fixture, 'high_elf_mage.yml')
    attacker = session.npc('goblin')
    base.add(attacker, 9, 16, group='b')
    upstairs.add(target_pc, 0, 0, group='a')

    battle = Battle(session, base)
    battle.add(attacker, 'b')
    battle.add(target_pc, 'a')
    battle.start()

    action = AttackAction(session, attacker, 'attack')
    action.using = 'dagger'
    valid = battle.valid_targets_for(attacker, action, target_types=['enemies'])
    assert target_pc in valid
