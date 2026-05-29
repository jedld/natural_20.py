"""Wire ``ConversationService`` and re-export its public helpers on ``app``."""
from webapp.conversation_service import ConversationService, register_conversation_routes
from webapp.llm_handler import read_npc_system_prompt


def wire_conversation_service(
    app,
    *,
    current_game_getter,
    game_session,
    socketio,
    entity_rag_handler_getter,
    llm_conversation_handler_getter,
    roles_for_username_getter,
    entity_owners_getter,
    entities_controlled_by_getter,
    logins_getter,
    logger,
    level,
):
    """Create conversation service, register routes, and return export bindings."""
    conversation_service = ConversationService(
        current_game_getter=current_game_getter,
        game_session=game_session,
        socketio=socketio,
        entity_rag_handler_getter=entity_rag_handler_getter,
        llm_conversation_handler_getter=llm_conversation_handler_getter,
        roles_for_username_getter=roles_for_username_getter,
        entity_owners_getter=entity_owners_getter,
        entities_controlled_by_getter=entities_controlled_by_getter,
        logins_getter=logins_getter,
        logger=logger,
    )

    register_conversation_routes(
        app,
        conversation_service,
        lambda: read_npc_system_prompt(level),
    )

    exports = {
        'conversation_service': conversation_service,
        'entity_audience_usernames': conversation_service.entity_audience_usernames,
        'conversation_audience_usernames': conversation_service.conversation_audience_usernames,
        'conversation_visible_whisper_usernames': conversation_service.conversation_visible_whisper_usernames,
        'conversation_payload': conversation_service.conversation_payload,
        'conversation_listener_for_username': conversation_service.conversation_listener_for_username,
        'listener_understands_language': conversation_service.listener_understands_language,
        'render_conversation_payload_for_username': conversation_service.render_conversation_payload_for_username,
        'resolve_conversation_targets': conversation_service.resolve_conversation_targets,
        'select_conversation_responders': conversation_service.select_conversation_responders,
        'emit_conversation_to_usernames': conversation_service.emit_conversation_to_usernames,
        'conversation_status_summary': conversation_service.conversation_status_summary,
        'conversation_effect_summary': conversation_service.conversation_effect_summary,
        'conversation_goal_summary': conversation_service.conversation_goal_summary,
        'conversation_attitude_toward_speaker': conversation_service.conversation_attitude_toward_speaker,
        'conversation_pressure_summary': conversation_service.conversation_pressure_summary,
        'conversation_response_prompt': conversation_service.conversation_response_prompt,
        'conversation_recipient_usernames': conversation_service.conversation_recipient_usernames,
        'effective_talk_volume': conversation_service.effective_talk_volume,
    }
    return conversation_service, exports
