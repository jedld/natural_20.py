from unittest.mock import Mock

from natural20.utils.conversation_witness import (
    log_witnessed_action,
    witnessed_action_lines,
    witness_entity_uids,
)


def test_witness_entity_uids_includes_source_and_target():
    source = Mock(entity_uid='finethir')
    target = Mock(entity_uid='aldric')
    uids = witness_entity_uids(None, source=source, target=target)
    assert uids == ['aldric', 'finethir']


def test_log_witnessed_action_scopes_visibility():
    logger = Mock()
    session = Mock()
    session.map_for_entity.return_value = None
    source = Mock(entity_uid='finethir')
    target = Mock(entity_uid='aldric')

    log_witnessed_action(logger, session, 'Aldric accepts scroll.', source=source, target=target)
    logger.log.assert_called_once()
    visibility = logger.log.call_args.kwargs['visibility']
    assert set(visibility['entity_uids']) == {'aldric', 'finethir'}


def test_witnessed_action_lines_for_observer():
    logger = Mock()
    observer = Mock(entity_uid='finethir')
    logger.get_visible_entries_for_entity.return_value = [
        {'message': '2026: Aldric accepts scroll.'},
    ]
    lines = witnessed_action_lines(logger, observer, limit=5)
    assert lines == ['2026: Aldric accepts scroll.']
