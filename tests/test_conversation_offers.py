from unittest.mock import Mock

from natural20.player_character import PlayerCharacter
from natural20.utils.conversation_offers import (
    adjust_item_offer_target,
    canonical_item_slug,
    evaluate_offer_block,
    format_available_offer_items,
    item_offer_suppression_note,
    listener_chose_item,
    offer_guidance_lines,
    record_completed_item_offer,
    requires_listener_disambiguation,
)


def test_canonical_item_slug_uses_campaign_aliases():
    configs = {
        'scroll_speak_animals_modified': {
            'aliases': ['scroll_speak_animals'],
        },
    }
    assert canonical_item_slug('scroll_speak_animals', configs) == 'scroll_speak_animals_modified'


def test_evaluate_offer_block_respects_completed_offer():
    session = Mock()
    session.load_state.return_value = {
        'completed': {'npc:pc:healing_potion': 5},
    }
    actor = Mock(entity_uid='npc', inventory={'healing_potion': {'qty': 1}})
    target = Mock(entity_uid='pc', inventory={})

    allowed, reason = evaluate_offer_block(
        session,
        actor,
        target,
        'healing_potion',
        game_properties={},
    )
    assert allowed is False
    assert reason == 'offer_completed'


def test_offer_guidance_includes_witnessed_block_reason():
    session = Mock()
    session.load_state.return_value = {}
    actor = Mock(entity_uid='finethir', inventory={})
    speaker = Mock(entity_uid='aldric', inventory={'scroll_speak_animals_modified': {'qty': 1}})

    game_properties = {
        'conversation_offer_guidance': {
            'target_has_item': '- {target} already has {item_label}.',
        },
        'conversation_item_offers': {
            'scroll_speak_animals_modified': {
                'item_label': 'scroll',
                'block_when': ['target_has_item'],
            },
        },
    }

    lines = offer_guidance_lines(
        session,
        actor,
        speaker,
        game_properties=game_properties,
        actor_has_map_item_fn=lambda _entity, _slug: True,
    )
    assert any('already has scroll' in line for line in lines)


def test_record_completed_item_offer_persists():
    session = Mock()
    session.game_time = 12
    session.load_state.return_value = {}
    actor = Mock(entity_uid='a')
    target = Mock(entity_uid='b')

    record_completed_item_offer(session, actor, target, 'item_x')
    session.save_state.assert_called_once()
    saved = session.save_state.call_args[0][1]
    assert saved['completed']['a:b:item_x'] == 12


def test_adjust_item_offer_target_prefers_player_over_npc_speaker():
    npc_speaker = Mock(entity_uid='pip_barmaid')
    pc = Mock(spec=PlayerCharacter, entity_uid='aldric')
    game_properties = {
        'conversation_item_offers': {
            'scroll_speak_animals_modified': {
                'prefer_player_character': True,
            },
        },
    }

    adjusted = adjust_item_offer_target(
        npc_speaker,
        target_spec='speaker',
        speaker=npc_speaker,
        player_speaker=pc,
        item_slug='scroll_speak_animals_modified',
        game_properties=game_properties,
    )
    assert adjusted is pc


def test_adjust_item_offer_target_respects_explicit_handle():
    npc_speaker = Mock(entity_uid='pip_barmaid')
    mara = Mock(entity_uid='mara_bartender')
    pc = Mock(spec=PlayerCharacter, entity_uid='aldric')
    game_properties = {
        'conversation_item_offers': {
            'scroll_speak_animals_modified': {
                'prefer_player_character': True,
            },
        },
    }

    adjusted = adjust_item_offer_target(
        mara,
        target_spec='@mara_bartender',
        speaker=npc_speaker,
        player_speaker=pc,
        item_slug='scroll_speak_animals_modified',
        game_properties=game_properties,
    )
    assert adjusted is mara


def test_offer_guidance_prefers_player_character_target():
    session = Mock()
    session.load_state.return_value = {}
    actor = Mock(entity_uid='finethir', inventory={'scroll_speak_animals_modified': {'qty': 1}})
    npc_speaker = Mock(entity_uid='pip_barmaid', inventory={})
    pc = Mock(spec=PlayerCharacter, entity_uid='aldric', inventory={})
    pc.label = Mock(return_value='Aldric')

    game_properties = {
        'conversation_item_offers': {
            'scroll_speak_animals_modified': {
                'item_label': 'scroll',
                'prefer_player_character': True,
                'block_when': ['target_has_item'],
            },
        },
    }

    lines = offer_guidance_lines(
        session,
        actor,
        npc_speaker,
        player_speaker=pc,
        game_properties=game_properties,
    )
    assert any('target=@aldric' in line for line in lines)
    assert any('not tavern staff' in line for line in lines)


def test_offer_guidance_lists_carried_inventory():
    session = Mock()
    session.load_state.return_value = {}
    actor = Mock(
        entity_uid='mara_bartender',
        inventory={
            'tavern_room_key_1': {'qty': 1},
            'tavern_room_key_2': {'qty': 1},
        },
    )
    game_properties = {
        'conversation_item_offers': {
            'tavern_room_key_1': {'item_label': 'Standard Room 1 key'},
            'tavern_room_key_2': {'item_label': 'Standard Room 2 key'},
        },
    }

    lines = offer_guidance_lines(
        session,
        actor,
        None,
        game_properties=game_properties,
    )
    assert any('Items you can hand over right now' in line for line in lines)
    assert any('tavern_room_key_1' in line for line in lines)


def test_item_offer_suppression_note_lists_available_items():
    actor = Mock(
        entity_uid='mara_bartender',
        inventory={
            'tavern_room_key_2': {'qty': 1},
        },
    )
    target = Mock(entity_uid='sable')
    game_properties = {
        'conversation_item_offers': {
            'tavern_room_key_1': {'item_label': 'Standard Room 1 key'},
            'tavern_room_key_2': {'item_label': 'Standard Room 2 key'},
        },
    }

    note = item_offer_suppression_note(
        actor,
        target,
        'tavern_room_key_1',
        'actor_lacks_item',
        game_properties=game_properties,
    )
    assert note is not None
    assert 'tavern_room_key_2' in note
    assert 'could not be completed' in note


def test_room_key_offer_blocked_until_guest_chooses_room():
    session = Mock()
    session.load_state.return_value = {}
    actor = Mock(
        entity_uid='mara',
        inventory={
            'tavern_room_key_1': {'qty': 1},
            'tavern_room_key_2': {'qty': 1},
        },
    )
    target = Mock(entity_uid='sable', inventory={})

    assert requires_listener_disambiguation(session, actor, 'tavern_room_key_1')

    allowed, reason = evaluate_offer_block(
        session,
        actor,
        target,
        'tavern_room_key_1',
        player_message='would you have any rooms to spare?',
    )
    assert allowed is False
    assert reason == 'listener_has_not_chosen'

    allowed, reason = evaluate_offer_block(
        session,
        actor,
        target,
        'tavern_room_key_1',
        player_message='I will take standard room 1 please',
    )
    assert allowed is True
    assert reason == 'ok'


def test_listener_chose_item_patterns():
    session = Mock()
    assert listener_chose_item(session, 'tavern_room_key_1', 'standard room 1 please')
    assert listener_chose_item(session, 'tavern_suite_key', 'the suite sounds good')
    assert not listener_chose_item(session, 'tavern_room_key_1', 'any rooms available?')
