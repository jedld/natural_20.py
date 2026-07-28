"""Tests for per-campaign SQLite text logs."""

import os
import tempfile

from natural20.campaign_log_db import CampaignLogDB


def test_append_and_list_by_category(tmp_path):
    db_path = os.path.join(tmp_path, 'campaign_logs.sqlite')
    db = CampaignLogDB(db_path)

    db.append('combat', 'Goblin hits for 5', visibility={'public': True})
    db.append_conversation(
        speaker_uid='pc1',
        speaker_label='Alice',
        message='Hello guards',
        target_labels=['Guard'],
        volume='normal',
    )
    db.append_dm_turn('user', 'How many goblins?')
    db.append_dm_turn('assistant', 'There are 3 goblins.')
    db.append_journal_entry('pc1', {
        'id': 'j1',
        'ts': '2026-05-19T12:00:00+00:00',
        'kind': 'note',
        'text': 'Found a secret door',
        'title': 'Exploration',
    })

    counts = db.counts_by_category()
    assert counts['combat'] == 1
    assert counts['conversation'] == 1
    assert counts['dm_assistant'] == 2
    assert counts['journal'] == 1

    dm_rows = db.dm_assistant_history_for_llm()
    assert dm_rows == [
        {'role': 'user', 'content': 'How many goblins?'},
        {'role': 'assistant', 'content': 'There are 3 goblins.'},
    ]

    combat_snap = db.combat_log_snapshot()
    assert len(combat_snap) == 1
    assert 'Goblin hits' in combat_snap[0]['message']


def test_context_lines_for_entity_filters_combat_and_conversation():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db = CampaignLogDB(os.path.join(tmp, 'logs.sqlite'))
        db.append(
            'combat',
            'Corin Vale takes 8 slashing damage',
            visibility={'kind': 'entities', 'entity_uids': ['corin_vale_guard', 'pc1']},
        )
        db.append('combat', 'A bird chirps somewhere distant', visibility={'public': True})
        db.append_conversation(
            speaker_uid='pc1',
            speaker_label='Alice',
            message='Corin, any trouble tonight?',
            targets=['corin_vale_guard'],
            target_labels=['Corin Vale'],
        )
        db.append_conversation(
            speaker_uid='stranger',
            speaker_label='Stranger',
            message='Nice weather',
            targets=[],
        )

        lines = db.context_lines_for_entity(
            'corin_vale_guard',
            handles={'corin', 'corin vale', 'corin_vale_guard'},
            combat_limit=10,
            conversation_limit=10,
        )
        assert any('Corin Vale takes' in line for line in lines['combat'])
        assert any('Alice' in line for line in lines['conversation'])
        assert not any('Nice weather' in line for line in lines['conversation'])


def test_clear_all():
    with tempfile.TemporaryDirectory() as tmp:
        db = CampaignLogDB(os.path.join(tmp, 'logs.sqlite'))
        db.append('combat', 'line')
        db.clear_all()
        assert db.counts_by_category() == {}
