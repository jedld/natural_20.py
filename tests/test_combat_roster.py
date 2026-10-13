import random

import pytest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils import combat_roster


class _Recorder:
    def __init__(self):
        self.entries = []

    def log(self, msg, event=None, visibility=None):
        self.entries.append((msg, visibility))

    def set_event_context(self, event):
        return None

    def clear_event_context(self):
        return None


@pytest.fixture
def world():
    random.seed(7000)
    em = EventManager()
    em.standard_cli()
    recorder = _Recorder()
    em.output_logger = recorder
    session = Session(root_path='tests/fixtures', event_manager=em)
    battle_map = Map(session, 'battle_sim')
    battle = Battle(session, battle_map)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle.add(fighter, 'a', position=(1, 5), token='F')
    battle.add(goblin, 'b', position=(4, 5), token='g')
    return session, battle, fighter, goblin, recorder


def _dm_lines(recorder):
    return [m for m, v in recorder.entries if v == 'dm']


def test_start_of_combat_logs_dm_roster(world):
    session, battle, fighter, goblin, recorder = world
    fighter.take_damage(3, battle=battle, damage_type='slashing')
    battle.start()
    dm = _dm_lines(recorder)
    assert dm[0].startswith('[DM] HP totals')
    assert f"team a: {fighter.hp()}/{fighter.max_hp()} HP" in dm[0]
    fighter_line = next(l for l in dm if l.startswith(f"[DM] {fighter.label()}"))
    assert f"starting HP {fighter.hp()}/{fighter.max_hp()}" in fighter_line
    assert f"AC {fighter.armor_class()}" in fighter_line
    assert 'gear:' in fighter_line and 'conditions:' in fighter_line
    goblin_line = next(l for l in dm if l.startswith(f"[DM] {goblin.label()}"))
    assert 'attacks: Scimitar (+4, 1d6+2 slashing)' in goblin_line
    public = [m for m, v in recorder.entries if v is None]
    assert not any('starting HP' in m for m in public)


def test_turn_start_logs_current_hp_for_dm(world):
    session, battle, fighter, goblin, recorder = world
    battle.start()
    fighter.take_damage(4, battle=battle, damage_type='slashing')
    fighter.statuses.append('prone')
    recorder.entries.clear()
    fighter.reset_turn(battle)
    dm = _dm_lines(recorder)
    assert len(dm) == 1, recorder.entries
    assert f"starts the turn at HP {fighter.hp()}/{fighter.max_hp()}" in dm[0]
    assert 'prone' in dm[0]


def test_campaign_can_disable_dm_summaries(world):
    session, battle, fighter, goblin, recorder = world
    session.game_properties = dict(session.game_properties or {}, combat_log=False)
    battle.start()
    fighter.reset_turn(battle)
    assert _dm_lines(recorder) == []


def test_item_summary_formats():
    assert combat_roster.item_summary(
        {'label': 'Longbow', 'damage': '1d8', 'damage_type': 'piercing', 'range': 150, 'range_max': 600}
    ) == 'Longbow (1d8 piercing; range 150/600)'
    assert combat_roster.item_summary({'label': 'Shield', 'bonus_ac': 2}) == 'Shield (+2 AC)'
    assert combat_roster.item_summary({'label': 'Chain Mail', 'ac': 16}) == 'Chain Mail (AC 16)'


def _briefing_entries(recorder):
    return [(m, v) for m, v in recorder.entries if isinstance(v, dict)]


def test_party_briefing_is_scoped_to_the_party(world):
    session, battle, fighter, goblin, recorder = world
    goblin.take_damage(4, battle=battle, damage_type='slashing')
    battle.start()
    entries = _briefing_entries(recorder)
    assert entries
    assert all(v['entity_uids'] == [str(fighter.entity_uid)] for _, v in entries)
    lines = [m for m, _ in entries]
    assert any(l.startswith(f"[Party] {fighter.label()}") and 'AC' in l for l in lines)
    foe = next(l for l in lines if l.startswith('[Foes]'))
    assert goblin.label() in foe and 'Appears' in foe
    assert 'HP' not in foe and 'AC' not in foe and '+4' not in foe
    assert 'Scimitar' in foe and foe.count('Shield') == 1


def test_party_briefing_omits_unseen_foes(world):
    session, battle, fighter, goblin, recorder = world
    goblin.do_hide(40)
    battle.start()
    lines = [m for m, _ in _briefing_entries(recorder)]
    assert not any(goblin.label() in l for l in lines if l.startswith('[Foes]'))
    assert '[Foes] No enemies are in sight.' in lines


def test_health_description_has_no_numbers(world):
    session, battle, fighter, goblin, recorder = world
    assert combat_roster.health_description(goblin) == 'unhurt'
    goblin.attributes['hp'] = 1
    assert combat_roster.health_description(goblin) == 'badly wounded'


def test_party_briefing_can_be_disabled(world):
    session, battle, fighter, goblin, recorder = world
    session.game_properties = dict(session.game_properties or {}, combat_log={'party_briefing': False})
    battle.start()
    assert _briefing_entries(recorder) == []
