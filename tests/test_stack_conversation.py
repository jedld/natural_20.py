"""Stack-aware conversation reachability and acoustics."""

import pytest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.conversation import acoustic_profile, conversation_reachability


@pytest.fixture
def stack_session():
    return Session(root_path='user_levels/wild_sheep_chase')


def test_cross_floor_conversation_at_stairs_is_reachable(stack_session):
    session = stack_session
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    fixture = Session(root_path='tests/fixtures', event_manager=EventManager())
    pc = PlayerCharacter.load(fixture, 'high_elf_mage.yml')
    npc = session.npc('goblin')
    npc.name = 'Mara'

    base.add(npc, 9, 16, group='b')
    upstairs.add(pc, 0, 0, group='a')

    battle = Battle(session, base)
    battle.add(npc, 'b')
    battle.add(pc, 'a')
    battle.start()

    entries = conversation_reachability(pc, upstairs, mode='normal', battle=battle)
    mara_entry = next((e for e in entries if e['entity'] is npc), None)
    assert mara_entry is not None
    assert mara_entry['reachable_now'] is True
    assert mara_entry['status'] == 'reachable'
    assert mara_entry['walls'] == 0

    profile = acoustic_profile(pc, npc, upstairs, battle=battle)
    assert profile['walls'] == 0
    assert profile['line_blocked'] is False


def test_tavern_bar_patron_has_no_false_wall_penalty(stack_session):
    """Patron at the Prancing Flagon bar should reach Mara at normal volume."""
    session = stack_session
    base = session.maps['town_market']
    mara = session.entity_by_uid('mara_bartender')
    assert mara is not None

    fixture = Session(root_path='tests/fixtures', event_manager=EventManager())
    pc = PlayerCharacter.load(fixture, 'high_elf_mage.yml')

    base.add(pc, 10, 19, group='a')
    battle = Battle(session, base)
    battle.add(mara, 'c')
    battle.add(pc, 'a')
    battle.start()

    profile = acoustic_profile(pc, mara, base, battle=battle)
    assert profile['walls'] == 0
    assert profile['penalty_ft'] == 0

    entries = conversation_reachability(pc, base, mode='normal', battle=battle)
    mara_entry = next((e for e in entries if e['entity'] is mara), None)
    assert mara_entry is not None
    assert mara_entry['reachable_now'] is True
    assert mara_entry['status'] == 'reachable'


def test_thin_left_wall_behind_bartender_does_not_block_patron(stack_session):
    """stone_wall_l only borders the left; speech from the taproom side is open."""
    session = stack_session
    base = session.maps['town_market']
    wall = next(
        obj for obj in base.objects_at(9, 20)
        if getattr(obj, 'border', None) is not None
    )
    assert wall.properties.get('type') == 'stone_wall_l'
    assert wall.opaque((10, 19)) is False
    assert wall.opaque((8, 20)) is True
