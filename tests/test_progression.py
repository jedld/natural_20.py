from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.progression import (
    adjusted_encounter_xp,
    encounter_difficulty,
    level_for_xp,
    normalize_progression_settings,
    split_xp,
    xp_for_cr,
)
from natural20.session import Session


def make_session():
    return Session(root_path='tests/fixtures', event_manager=EventManager())


def test_5e_2014_xp_thresholds_and_cr_values():
    assert level_for_xp(0) == 1
    assert level_for_xp(299) == 1
    assert level_for_xp(300) == 2
    assert level_for_xp(6500) == 5
    assert level_for_xp(355000) == 20
    assert xp_for_cr("1/4") == 50
    assert xp_for_cr(2) == 450


def test_encounter_adjustment_and_split():
    session = make_session()
    goblins = [session.npc('goblin'), session.npc('goblin')]
    assert adjusted_encounter_xp(goblins, party_size=4) == 150
    assert encounter_difficulty(150, [1, 1, 1, 1]) == 'easy'

    class Recipient:
        def __init__(self, entity_uid):
            self.entity_uid = entity_uid

    assert split_xp(101, [Recipient('a'), Recipient('b')], split=True) == {'a': 51, 'b': 50}


def test_player_character_xp_and_level_up_average_hp():
    session = make_session()
    pc = PlayerCharacter.load(session, 'high_elf_mage.yml')
    pc.add_experience(300, source='test')

    assert pc.experience() == 300
    assert pc.pending_level_ups() == 1

    preview = pc.level_up_preview()
    assert preview['new_level'] == 2
    assert preview['class_name'] == 'wizard'
    assert preview['hp']['gain'] == 6
    assert preview['spell_slot_changes'][1] == {'old': 2, 'new': 3}

    pc.consume_spell_slot(1, 'wizard')
    summary = pc.apply_level_up()
    assert summary['new_level'] == 2
    assert pc.level() == 2
    assert pc.properties['classes']['wizard'] == 2
    assert pc.max_hp() == 12
    assert pc.hp() == 12
    assert pc.spell_slots_count(1, 'wizard') == 2
    assert pc.pending_level_ups() == 0
    assert pc.properties['level_history']


def test_dm_gated_progression_ignores_xp_until_granted():
    session = make_session()
    session.game_properties['progression'] = {'mode': 'dm'}
    pc = PlayerCharacter.load(session, 'high_elf_mage.yml')
    pc.add_experience(900, source='test')

    assert pc.pending_level_ups() == 0
    grants = pc.grant_level_up(reason='story milestone')
    assert len(grants) == 1
    assert pc.pending_level_ups() == 1

    summary = pc.apply_level_up()
    assert summary['grant']['reason'] == 'story milestone'
    assert pc.level() == 2
    assert pc.pending_level_ups() == 0


def test_event_gated_progression_requires_configured_event():
    session = make_session()
    session.game_properties['progression'] = {
        'mode': 'event',
        'events': {
            'rescued_prince': {'levels': 1, 'label': 'Rescued the Prince'}
        },
    }
    pc = PlayerCharacter.load(session, 'high_elf_mage.yml')

    grants = pc.grant_event_level_up('rescued_prince')
    assert grants[0]['event'] == 'rescued_prince'
    assert pc.pending_level_ups() == 1


def test_progression_settings_normalize_event_list():
    settings = normalize_progression_settings({
        'mode': 'event',
        'level_up_events': ['first_boss'],
    })
    assert settings['mode'] == 'event'
    assert settings['events']['first_boss']['levels'] == 1
