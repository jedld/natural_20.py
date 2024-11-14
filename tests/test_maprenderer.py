import pytest
from unittest import mock
import time
from natural20.map_renderer import MapRenderer
from natural20.session import Session
from natural20.map import Map
from natural20.player_character import PlayerCharacter
import pdb


@pytest.fixture
def setup():
    with mock.patch('builtins.print'), mock.patch('time.sleep'):
        session = Session(root_path='tests/fixtures')
        battle_map = Map(session, 'large_map')
        map_renderer = MapRenderer(battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        battle_map.place((0, 1), fighter, 'G')
        yield map_renderer, fighter

def test_able_to_render_a_map(setup):
    map_renderer, fighter = setup
    start_time = time.time()
    result = map_renderer.render(line_of_sight=fighter)
    duration = time.time() - start_time
    print(duration)
    print(result)
    expected_result = ("···········****····*····**g···\n" +
                       "G·······*********·····****····\n" +
                       "·······**********····****·····\n" +
                       "·········**g****······**······\n" +
                       "------------------------------\n" +
                       "······························\n" * 11)
    assert result == expected_result

def test_able_to_render_with_range_limit(setup):
    map_renderer, fighter = setup
    result = map_renderer.render(entity=fighter, range_value=3, range_cutoff=True)
    print(result)
    expected_result = ("····                          \n" * 16)
    assert result == expected_result
