"""Rules-bound tactical communication between combatants.

D&D 5e (PHB "Other Activity on Your Turn"): a creature can communicate,
however it is able, through brief utterances and gestures *as it takes its
turn*. This module turns that into a fair channel for AI-controlled
combatants (LLM and JEV controllers) to coordinate:

* **Speaker** — only on its own turn, at most one callout per turn, a brief
  utterance (word cap). It must be able to speak: not dead, unconscious,
  asleep, paralyzed, petrified, in magical silence, or in a beast form, and
  it must know a language. Stunned creatures speak only falteringly (tighter
  word cap). Creatures with ``telepathy: <ft>`` may instead send a silent
  message to allies in range who understand at least one language.
* **Listener** — hears through the shared speech acoustics
  (``natural20.utils.conversation``: whisper 5 ft / normal 30 ft / shout
  60 ft, walls and doors muffle). It must be conscious and not deafened or
  inside magical silence, and it only *understands* the content when it
  comprehends the language.
* **Fairness** — spoken callouts are not private: enemies within earshot who
  understand the language overhear them. A callout target must be something
  the speaker can currently see. Heard callouts only inform the listener's
  *next* decision; nothing grants extra actions or reactions.

Every in-combat utterance that goes through ``Entity.send_conversation``
(AI callouts, ``SpeakAction``, a human player's chat) is recorded into the
``heard_callouts`` list of each combatant that heard it. That list lives in
the battle's per-entity state, so it is shared by every controller instance
and survives save/load.

Campaign switch (``game.yml``)::

    combat_communication:
      enabled: true          # default true
      max_words: 20          # brief utterance cap (~6 seconds of speech)
      memory_rounds: 1       # how many rounds a heard callout stays relevant
      auto_callouts: true    # JEV / decision-only controllers announce focus & calls for aid
      strategic_callouts: true  # JEV picks the callout from a combat-data menu (one extra decision)
      llm_phrasing: true     # the conversation LLM voices callouts in character
      default_volume: shout  # whisper | normal | shout

``N20_COMBAT_COMMS=0`` disables the feature globally.

Callouts without explicit wording (JEV, auto callouts) are phrased by an
optional *phraser* installed by the host app (``set_callout_phraser``); the
webapp wires its NPC conversation LLM. A creature opts out with
``callout_phrasing: false``. Without a phraser, or when it fails, a short
template line is used.
"""

from __future__ import annotations

import os
import weakref
from typing import Any, Dict, List, Optional

from natural20.utils import combat_intelligence
from natural20.utils.conversation import SPEECH_BASE_RANGES, delivered_conversations
from natural20.utils.language_comprehension import comprehends_speech, normalize_language

CALLOUT_KINDS = ('focus', 'heal', 'help', 'warn', 'retreat', 'protect', 'taunt', 'revive', 'regroup', 'say')
# Orders and requests only an ally can act on; with no conscious ally in the
# fight they are pointless.
ALLY_DIRECTED_KINDS = frozenset({'focus', 'heal', 'help', 'warn', 'retreat', 'protect', 'revive', 'regroup'})

DEFAULT_SETTINGS = {
    'enabled': True,
    'max_words': 20,
    'memory_rounds': 1,
    'auto_callouts': True,
    'strategic_callouts': True,
    'llm_phrasing': True,
    'default_volume': 'shout',
}

STUNNED_MAX_WORDS = 3
MAX_INBOX = 8
STATE_KEY = 'heard_callouts'
SPOKE_KEY = 'last_callout_turn'

_SPEECH_BLOCKING_STATUSES = ('dead', 'unconscious', 'sleep', 'paralyzed', 'petrified')
_HEARING_BLOCKING_STATUSES = ('dead', 'unconscious', 'sleep', 'petrified', 'deafened')

_BATTLES: 'weakref.WeakSet' = weakref.WeakSet()


# --------------------------------------------------------------------------- #
# Battle registry                                                             #
# --------------------------------------------------------------------------- #

def register_battle(battle) -> None:
    try:
        _BATTLES.add(battle)
    except TypeError:
        pass


def battle_for(entity) -> Optional[Any]:
    """Return a live battle that includes *entity*, if any."""
    if entity is None:
        return None
    for battle in list(_BATTLES):
        try:
            if battle.entity_state_for(entity) is not None:
                return battle
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------- #
# Settings                                                                    #
# --------------------------------------------------------------------------- #

def settings_for(session) -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    props = getattr(session, 'game_properties', None) or {}
    raw = props.get('combat_communication') if isinstance(props, dict) else None
    if isinstance(raw, bool):
        out['enabled'] = raw
    elif isinstance(raw, dict):
        out.update({k: v for k, v in raw.items() if k in DEFAULT_SETTINGS})
    env = os.getenv('N20_COMBAT_COMMS')
    if env is not None and env.strip().lower() in ('0', 'false', 'no', 'off'):
        out['enabled'] = False
    return out


def enabled(session) -> bool:
    return bool(settings_for(session).get('enabled'))


# --------------------------------------------------------------------------- #
# Rules: who can speak / hear                                                 #
# --------------------------------------------------------------------------- #

def _statuses(entity) -> set:
    return {str(s) for s in (getattr(entity, 'statuses', None) or [])}


def _in_silence(entity) -> bool:
    from natural20.utils.message_spell_path import entity_in_magical_silence
    try:
        return entity_in_magical_silence(entity)
    except Exception:
        return False


def _in_beast_form(entity) -> bool:
    try:
        from natural20.utils.polymorph import has_assumed_form
        return bool(has_assumed_form(entity))
    except Exception:
        return False


def _languages(entity) -> List[str]:
    try:
        langs = entity.languages() or []
    except Exception:
        langs = []
    return [normalize_language(lang) for lang in langs if lang]


def telepathy_range(entity) -> int:
    props = getattr(entity, 'properties', None) or {}
    try:
        return int(props.get('telepathy') or 0)
    except (TypeError, ValueError):
        return 0


def speech_block_reason(entity) -> Optional[str]:
    """Why *entity* cannot speak right now (None when it can)."""
    if entity is None:
        return 'no_speaker'
    sts = _statuses(entity)
    for status in _SPEECH_BLOCKING_STATUSES:
        if status in sts:
            return status
    try:
        if entity.dead():
            return 'dead'
        if entity.unconscious():
            return 'unconscious'
    except Exception:
        pass
    if _in_silence(entity):
        return 'silenced'
    if _in_beast_form(entity):
        return 'beast_form'
    if not _languages(entity):
        return 'no_language'
    return None


def telepathy_block_reason(entity) -> Optional[str]:
    if telepathy_range(entity) <= 0:
        return 'no_telepathy'
    sts = _statuses(entity)
    for status in _SPEECH_BLOCKING_STATUSES:
        if status in sts:
            return status
    try:
        if entity.dead() or entity.unconscious():
            return 'unconscious'
    except Exception:
        pass
    return None


def can_hear(listener) -> bool:
    if listener is None:
        return False
    sts = _statuses(listener)
    if any(s in sts for s in _HEARING_BLOCKING_STATUSES):
        return False
    try:
        if listener.dead() or listener.unconscious():
            return False
    except Exception:
        pass
    return not _in_silence(listener)


def max_words_for(entity, session=None) -> int:
    cap = int(settings_for(session or getattr(entity, 'session', None)).get('max_words') or 20)
    cap = combat_intelligence.max_callout_words(entity, cap)
    if 'stunned' in _statuses(entity):
        cap = min(cap, STUNNED_MAX_WORDS)
    return max(1, cap)


def brief(text: str, max_words: int) -> str:
    words = str(text or '').split()
    if len(words) <= max_words:
        return ' '.join(words)
    return ' '.join(words[:max_words]).rstrip(',;:') + '...'


# --------------------------------------------------------------------------- #
# Turn window                                                                 #
# --------------------------------------------------------------------------- #

def _turn_marker(battle) -> List[int]:
    return [int(getattr(battle, 'round', 0) or 0), int(getattr(battle, 'current_turn_index', 0) or 0)]


def _is_current_turn(battle, entity) -> bool:
    try:
        current = battle.current_turn()
    except Exception:
        return False
    if current is None:
        return False
    if current is entity:
        return True
    return getattr(current, 'entity_uid', None) is not None and \
        getattr(current, 'entity_uid', None) == getattr(entity, 'entity_uid', None)


def has_spoken_this_turn(battle, entity) -> bool:
    state = battle.entity_state_for(entity) if battle is not None else None
    if not state:
        return False
    return list(state.get(SPOKE_KEY) or []) == _turn_marker(battle)


def window_block_reason(battle, entity) -> Optional[str]:
    """Why *entity* may not issue a callout now (None when it may)."""
    if battle is None:
        return 'no_battle'
    session = getattr(battle, 'session', None)
    if not enabled(session):
        return 'disabled'
    if battle.entity_state_for(entity) is None:
        return 'not_in_battle'
    if not _is_current_turn(battle, entity):
        return 'not_your_turn'
    if has_spoken_this_turn(battle, entity):
        return 'already_spoke'
    return None


def can_call_out(battle, entity) -> bool:
    if window_block_reason(battle, entity) is not None:
        return False
    if not combat_intelligence.can_coordinate(entity):
        return False
    return speech_block_reason(entity) is None or telepathy_block_reason(entity) is None


# --------------------------------------------------------------------------- #
# Recording what was heard                                                    #
# --------------------------------------------------------------------------- #

def _safe_name(entity) -> str:
    try:
        label = entity.label() if callable(getattr(entity, 'label', None)) else None
    except Exception:
        label = None
    return str(label or getattr(entity, 'name', None) or entity)


def _append_inbox(battle, listener, entry: dict) -> None:
    state = battle.entity_state_for(listener)
    if state is None:
        return
    inbox = [e for e in (state.get(STATE_KEY) or []) if isinstance(e, dict)]
    inbox.append(entry)
    min_round = int(getattr(battle, 'round', 0) or 0) - int(
        settings_for(getattr(battle, 'session', None)).get('memory_rounds') or 1)
    inbox = [e for e in inbox if int(e.get('round', 0) or 0) >= min_round]
    state[STATE_KEY] = inbox[-MAX_INBOX:]


def record_speech(speaker, message: str, language: str, deliveries: List[dict],
                  callout: Optional[dict] = None, battle=None) -> List[Any]:
    """Store an utterance in the inbox of every combatant that heard it.

    *deliveries* is the acoustic delivery list from ``delivered_conversations``
    (listeners actually within earshot). Returns the listeners recorded.
    """
    battle = battle or battle_for(speaker)
    if battle is None or not enabled(getattr(battle, 'session', None)):
        return []
    if battle.entity_state_for(speaker) is None:
        return []
    callout = callout or {}
    session = getattr(battle, 'session', None)
    recorded = []
    for delivery in deliveries or []:
        listener = delivery.get('entity')
        if listener is None or listener is speaker:
            continue
        if battle.entity_state_for(listener) is None:
            continue
        telepathic = bool(callout.get('telepathic'))
        if not telepathic and not can_hear(listener):
            continue
        understood = telepathic or comprehends_speech(listener, language, source=speaker, session=session)
        entry = {
            'from_uid': getattr(speaker, 'entity_uid', None),
            'from': _safe_name(speaker),
            'round': int(getattr(battle, 'round', 0) or 0),
            'kind': callout.get('kind') or 'say',
            'target_uid': callout.get('target_uid') if understood else None,
            'target': callout.get('target') if understood else None,
            'text': message if understood else None,
            'language': language,
            'volume': callout.get('volume'),
            'mode': callout.get('mode') or 'speech',
            'understood': bool(understood),
        }
        _append_inbox(battle, listener, entry)
        recorded.append(listener)
    if callout is not None:
        callout['heard'] = recorded
    return recorded


def heard_callouts(battle, listener) -> List[dict]:
    """Callouts *listener* heard that are still relevant (memory window)."""
    state = battle.entity_state_for(listener) if battle is not None else None
    if not state:
        return []
    min_round = int(getattr(battle, 'round', 0) or 0) - int(
        settings_for(getattr(battle, 'session', None)).get('memory_rounds') or 1)
    return [e for e in (state.get(STATE_KEY) or [])
            if isinstance(e, dict) and int(e.get('round', 0) or 0) >= min_round]


def _entity_by_uid(battle, uid):
    if not uid:
        return None
    session = getattr(battle, 'session', None)
    try:
        return session.entity_by_uid(uid) if session is not None else None
    except Exception:
        return None


def _relation(battle, listener, entry) -> str:
    speaker = _entity_by_uid(battle, entry.get('from_uid'))
    if speaker is None:
        return 'unknown'
    try:
        if battle.allies(listener, speaker):
            return 'ally'
        if battle.opposing(listener, speaker):
            return 'enemy'
    except Exception:
        pass
    return 'neutral'


def callout_lines(battle, listener, max_lines: int = 6) -> List[str]:
    """Prompt-ready lines for what *listener* heard recently, limited to what
    its intelligence lets it act on (see ``combat_intelligence``)."""
    out = []
    usable = []
    for entry in heard_callouts(battle, listener):
        rel = _relation(battle, listener, entry)
        if entry.get('understood') and not combat_intelligence.comprehends_callout(listener, entry):
            continue
        if rel == 'enemy' and not combat_intelligence.exploits_overheard_enemies(listener):
            continue
        if not combat_intelligence.can_coordinate(listener):
            continue
        usable.append((rel, entry))
    for rel, entry in usable[-max_lines:]:
        who = entry.get('from') or 'someone'
        how = 'telepathically' if entry.get('mode') == 'telepathy' else (entry.get('volume') or 'said')
        prefix = f"[{rel}] {who} (round {entry.get('round')}, {how})"
        if not entry.get('understood'):
            out.append(f"{prefix}: spoke in {entry.get('language')} - you could not understand it")
            continue
        line = f"{prefix}: \"{entry.get('text')}\""
        kind = entry.get('kind')
        if kind and kind != 'say':
            line += f" [{kind}"
            target = _entity_by_uid(battle, entry.get('target_uid'))
            if entry.get('target'):
                line += f" -> {entry['target']}"
                try:
                    if target is not None and (target.dead() or target.unconscious()):
                        line += " (now down)"
                except Exception:
                    pass
            line += "]"
        out.append(line)
    return out


def ally_focus_target(battle, listener):
    """Most recent still-standing focus target called by an understood ally."""
    if not combat_intelligence.can_coordinate(listener):
        return None
    for entry in reversed(heard_callouts(battle, listener)):
        if entry.get('kind') != 'focus' or not entry.get('understood'):
            continue
        if _relation(battle, listener, entry) != 'ally':
            continue
        target = _entity_by_uid(battle, entry.get('target_uid'))
        try:
            if target is not None and not target.dead() and not target.unconscious():
                return target
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------- #
# Issuing callouts                                                            #
# --------------------------------------------------------------------------- #

_KIND_TEMPLATES = {
    'focus': "Focus on {target}!",
    'heal': "I need healing!",
    'help': "Help me with {target}!",
    'warn': "Watch out for {target}!",
    'retreat': "Fall back!",
    'protect': "Protect {target}!",
    'taunt': "Come at me, {target}!",
    'revive': "Get {target} back up!",
    'regroup': "Regroup, cover the fallen!",
}

_PHRASER = None


def set_callout_phraser(phraser) -> None:
    """Install ``phraser(request: dict) -> str | None`` for in-character callout wording.

    *request* keys: ``speaker``, ``battle``, ``kind``, ``target`` (entity or
    None), ``target_name``, ``target_unconscious``, ``intent``,
    ``default_text``, ``max_words``, ``language``, ``telepathic``,
    ``recent_lines`` (the speaker's last phrased callouts this battle).
    Pass ``None`` to remove it.
    """
    global _PHRASER
    _PHRASER = phraser


def get_callout_phraser():
    return _PHRASER


def _clean_phrase(text: Optional[str], max_words: int) -> Optional[str]:
    if not text:
        return None
    line = next((ln.strip() for ln in str(text).splitlines() if ln.strip()), '')
    if not line or 'NO_RESPONSE' in line.upper():
        return None
    if ':' in line[:40] and not line.startswith('"'):
        head, _, rest = line.partition(':')
        if len(head.split()) <= 4 and rest.strip():
            line = rest.strip()
    line = line.strip('*_ ').strip('"\u201c\u201d\'').strip()
    return brief(line, max_words) if line else None


def _phrase(battle, speaker, kind, target_entity, target_name, default_text, max_words,
            language, telepathic, intent) -> str:
    phraser = _PHRASER
    session = getattr(battle, 'session', None)
    if phraser is None or not settings_for(session).get('llm_phrasing'):
        return default_text
    props = getattr(speaker, 'properties', None) or {}
    if isinstance(props, dict) and props.get('callout_phrasing') is False:
        return default_text
    state = None
    try:
        state = battle.entity_state_for(speaker) if battle is not None else None
    except Exception:
        state = None
    spoken = state.setdefault('spoken_callouts', []) if isinstance(state, dict) else []
    heard = [e.get('text') for e in heard_callouts(battle, speaker)
             if e.get('text') and e.get('from_uid') != getattr(speaker, 'entity_uid', None)]
    recent = list(dict.fromkeys(spoken[-4:] + heard[-4:]))
    target_down = False
    try:
        target_down = target_entity is not None and not target_entity.conscious()
    except Exception:
        pass
    try:
        text = phraser({
            'speaker': speaker, 'battle': battle, 'kind': kind,
            'target': target_entity, 'target_name': target_name,
            'target_unconscious': target_down,
            'intent': intent or default_text, 'default_text': default_text,
            'max_words': max_words, 'language': language, 'telepathic': bool(telepathic),
            'recent_lines': recent,
        })
    except Exception:
        return default_text
    line = _clean_phrase(text, max_words) or default_text
    spoken.append(line)
    del spoken[:-8]
    return line


def _choose_language(battle, speaker, requested: Optional[str]) -> str:
    known = _languages(speaker)
    if requested:
        req = normalize_language(requested)
        if req in known:
            return req
    session = getattr(battle, 'session', None)
    allies, enemies = [], []
    try:
        allies = [a for a in battle.allies_of(speaker) if a is not speaker and can_hear(a)]
        if combat_intelligence.tactics_tier(speaker) == 'mastermind':
            enemies = [e for e in battle.opponents_of(speaker) if can_hear(e)]
    except Exception:
        pass

    def count(group, lang):
        return sum(1 for a in group if comprehends_speech(a, lang, source=speaker, session=session))

    best = sorted(known, key=lambda lang: (-count(allies, lang), count(enemies, lang), lang != 'common', lang))
    return best[0] if best else 'common'


def _resolve_target(battle, speaker, target):
    if target is None or target == '':
        return None
    if not isinstance(target, str):
        return target
    name = target.strip().lower()
    for e in list(getattr(battle, 'entities', {}).keys()):
        try:
            if _safe_name(e).lower() == name or str(getattr(e, 'name', '')).lower() == name:
                return e
        except Exception:
            continue
    return None


def _telepathy_recipients(battle, speaker, distance_ft: int) -> List[Any]:
    m = battle.map_for(speaker)
    out = []
    for ally in battle.allies_of(speaker):
        if ally is speaker:
            continue
        try:
            if ally.dead() or ally.unconscious() or not _languages(ally):
                continue
            if m is not None and m.distance(speaker, ally) * m.feet_per_grid > distance_ft:
                continue
        except Exception:
            continue
        out.append(ally)
    return out


def issue_callout(battle, speaker, kind: str = 'say', target=None, message: Optional[str] = None,
                  language: Optional[str] = None, volume: Optional[str] = None,
                  telepathic: Optional[bool] = None, intent: Optional[str] = None) -> Dict[str, Any]:
    """Have *speaker* call out to the battlefield, following 5e rules.

    Without *message*, the installed phraser voices *intent* (or the kind's
    template) in character; the structured ``kind``/``target`` is unchanged.

    Returns ``{'ok': bool, 'reason': str|None, 'text': str, 'heard_by': [...],
    'overheard_by_enemies': [...]}``.
    """
    result = {'ok': False, 'reason': None, 'text': '', 'heard_by': [], 'overheard_by_enemies': []}
    reason = window_block_reason(battle, speaker)
    if reason:
        result['reason'] = reason
        return result

    kind = str(kind or 'say').strip().lower()
    if kind not in CALLOUT_KINDS:
        kind = 'say'
    if not combat_intelligence.can_coordinate(speaker):
        result['reason'] = 'too_simple'
        return result
    if not combat_intelligence.allowed_callout_kind(speaker, kind):
        if not message:
            result['reason'] = 'too_simple'
            return result
        kind = 'say'

    if kind in ALLY_DIRECTED_KINDS and not _has_listening_ally(battle, speaker):
        result['reason'] = 'no_listening_ally'
        return result

    target_entity = _resolve_target(battle, speaker, target)
    if target_entity is not None and target_entity is not speaker:
        try:
            if not battle.can_see(speaker, target_entity):
                result['reason'] = 'target_not_visible'
                return result
        except Exception:
            pass
    if kind in ('focus', 'warn', 'protect', 'taunt', 'revive') and target_entity is None:
        if not message:
            result['reason'] = 'missing_target'
            return result

    speech_reason = speech_block_reason(speaker)
    tele_reason = telepathy_block_reason(speaker)
    use_telepathy = bool(telepathic) if telepathic is not None else (speech_reason is not None)
    if use_telepathy and tele_reason is not None:
        use_telepathy = False
    if not use_telepathy and speech_reason is not None:
        result['reason'] = speech_reason
        return result

    session = getattr(battle, 'session', None)
    target_name = _safe_name(target_entity) if target_entity is not None else None
    max_words = max_words_for(speaker, session)
    lang = 'telepathy' if use_telepathy else _choose_language(battle, speaker, language)
    text = (message or '').strip()
    if not text:
        template = _KIND_TEMPLATES.get(kind)
        text = template.format(target=target_name or 'them') if template else ''
        if text:
            text = _phrase(battle, speaker, kind, target_entity, target_name, text, max_words,
                           lang, use_telepathy, intent)
    if not text:
        result['reason'] = 'empty_message'
        return result
    text = brief(text, max_words)

    meta = {
        'kind': kind,
        'target': target_name,
        'target_uid': getattr(target_entity, 'entity_uid', None) if target_entity is not None else None,
    }

    if use_telepathy:
        recipients = _telepathy_recipients(battle, speaker, telepathy_range(speaker))
        meta.update(mode='telepathy', volume='telepathy', telepathic=True)
        record_speech(speaker, text, lang, [{'entity': r} for r in recipients], callout=meta, battle=battle)
        if session is not None and recipients:
            session.event_manager.received_event({
                'source': speaker, 'event': 'conversation', 'message': text,
                'language': lang, 'targets': recipients, 'distance_ft': 0, 'volume': 'whisper',
            })
    else:
        vol = str(volume or settings_for(session).get('default_volume') or 'shout').lower()
        if vol not in SPEECH_BASE_RANGES:
            vol = 'shout'
        meta.update(mode='speech', volume=vol)
        speaker.send_conversation(text, distance_ft=SPEECH_BASE_RANGES[vol], language=lang,
                                  volume=vol, callout=meta)
    heard = meta.get('heard') or []

    state = battle.entity_state_for(speaker)
    if state is not None:
        state[SPOKE_KEY] = _turn_marker(battle)

    result.update(ok=True, text=text, language=lang)
    for listener in heard:
        try:
            if battle.allies(listener, speaker):
                result['heard_by'].append(_safe_name(listener))
            elif battle.opposing(listener, speaker):
                entry = (battle.entity_state_for(listener) or {}).get(STATE_KEY) or []
                if entry and entry[-1].get('understood'):
                    result['overheard_by_enemies'].append(_safe_name(listener))
        except Exception:
            continue
    return result


# --------------------------------------------------------------------------- #
# Automatic callouts (decision-only controllers such as JEV)                  #
# --------------------------------------------------------------------------- #

def _has_listening_ally(battle, speaker) -> bool:
    try:
        return any(a is not speaker and can_hear(a) for a in battle.allies_of(speaker))
    except Exception:
        return False


def auto_callout(battle, speaker, action=None, chooser=None) -> Optional[Dict[str, Any]]:
    """Callout for controllers that cannot generate speech (e.g. JEV).

    Builds the strategic menu (``combat_strategy.strategy_options``) from what
    the speaker perceives. *chooser* ``(options) -> option | None`` picks one
    (``kind: None`` means stay silent); it is used only when
    ``strategic_callouts`` is on. Without a chooser, or when it fails
    (returns ``None``), the deterministic pick applies: call for healing when
    nearly down, otherwise announce the enemy being attacked unless an ally
    already called that focus. The chosen option's intent is voiced by the
    phraser (see ``set_callout_phraser``).
    """
    session = getattr(battle, 'session', None) if battle is not None else None
    settings = settings_for(session)
    if battle is None or not settings.get('auto_callouts'):
        return None
    if not can_call_out(battle, speaker) or not _has_listening_ally(battle, speaker):
        return None
    from natural20.utils import combat_strategy
    options = combat_strategy.strategy_options(battle, speaker, action)
    choice = None
    if chooser is not None and settings.get('strategic_callouts') and len(options) > 1:
        try:
            choice = chooser(options)
        except Exception:
            choice = None
    if choice is None:
        choice = combat_strategy.default_choice(battle, speaker, options, action)
    if not choice or not choice.get('kind'):
        return None
    return issue_callout(battle, speaker, kind=choice['kind'], target=choice.get('target'),
                         intent=choice.get('intent'))
