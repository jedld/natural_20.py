"""Active Message cantrip whisper links (caster ↔ target, short reply window)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


DEFAULT_REPLY_WINDOW_SECONDS = 120.0


@dataclass
class MessageSpellLink:
    id: str
    caster: Any
    target: Any
    map_name: str
    cast_round: int | None = None
    expires_at_game_time: int = 0
    created_at_wall: float = field(default_factory=time.time)
    reply_window_seconds: float = DEFAULT_REPLY_WINDOW_SECONDS

    def other_party(self, speaker):
        if speaker is self.caster:
            return self.target
        if speaker is self.target:
            return self.caster
        return None

    def can_speak(self, speaker) -> bool:
        return speaker is self.caster or speaker is self.target

    def is_active(self, session, battle=None) -> bool:
        if time.time() - self.created_at_wall > self.reply_window_seconds:
            return False
        if session is not None and self.expires_at_game_time and session.game_time > self.expires_at_game_time:
            return False
        if self.cast_round is not None and battle is not None and getattr(battle, 'started', False):
            if getattr(battle, 'round', 0) > self.cast_round:
                return False
        return True


def register_message_spell_link(session, link: MessageSpellLink) -> None:
    if not hasattr(session, 'message_spell_links') or session.message_spell_links is None:
        session.message_spell_links = {}
    session.message_spell_links[link.id] = link


def get_message_spell_link(session, link_id: str | None) -> MessageSpellLink | None:
    if not link_id or session is None:
        return None
    links = getattr(session, 'message_spell_links', None) or {}
    link = links.get(link_id)
    return link if isinstance(link, MessageSpellLink) else None


def create_message_spell_link(
    session,
    caster,
    target,
    battle_map,
    *,
    battle=None,
    duration_seconds: int = 6,
) -> MessageSpellLink:
    cast_round = getattr(battle, 'round', None) if battle is not None and getattr(battle, 'started', False) else None
    game_time = int(getattr(session, 'game_time', 0) or 0)
    link = MessageSpellLink(
        id=str(uuid.uuid4()),
        caster=caster,
        target=target,
        map_name=getattr(battle_map, 'name', '') or '',
        cast_round=cast_round,
        expires_at_game_time=game_time + max(int(duration_seconds or 6), 6),
    )
    register_message_spell_link(session, link)
    return link
