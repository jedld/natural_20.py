"""Battle psychology for AI combatants: nerve, courage and character flaws.

Intelligence (``natural20.utils.combat_intelligence``) decides *how clever* a
creature's tactics are. This module decides *how brave* it is: whether it
stands and fights, breaks and runs, or charges regardless of the odds. Both
feed the same places — the hybrid LLM strategist's plan prompt, the JEV state
context, the deterministic ``GenericController``'s movement and the move-leaf
menu.

Authoring (NPC / character YAML, all optional)::

    combat_personality: cowardly          # one tag or a list of tags
    combat_personality: [cowardly, greedy]

    morale:
      stance: flighty                     # flighty|cautious|normal|steadfast|fearless|reckless
      flee_at_hp: 0.5                     # fraction of max HP where nerve breaks
                                          # (1.0 = runs from the first blow, 0 = never)
      flee_when_outnumbered: true
      never_flee: false
      ignores_self_preservation: false    # alias of never_flee

    combat_weaknesses:                    # free text shown to the battle AI
      - "sunlight: it flees from open daylight"

When ``combat_personality`` / ``morale`` are absent the disposition is
*inferred* from the creature's own profile text (``personality_traits``,
``flaws``, ``ideals``, ``bonds``, ``backstory``, ``description``), so an
imported character written as "I am a coward who runs from any fight" already
fights like a coward. Undead, constructs and creatures with the ``fearless``
class feature never break.

Nothing here is persisted: the "nerve has broken" latch lives in battle entity
state (``morale_broken``), so it resets when the fight ends.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: Battle entity state key latching a broken morale for the rest of the fight.
MORALE_STATE_KEY = 'morale_broken'

# --------------------------------------------------------------------------- #
# Stances                                                                     #
# --------------------------------------------------------------------------- #

STANCE_FLIGHTY = 'flighty'
STANCE_CAUTIOUS = 'cautious'
STANCE_NORMAL = 'normal'
STANCE_STEADFAST = 'steadfast'
STANCE_FEARLESS = 'fearless'
STANCE_RECKLESS = 'reckless'

STANCES = (STANCE_FLIGHTY, STANCE_CAUTIOUS, STANCE_NORMAL,
           STANCE_STEADFAST, STANCE_FEARLESS, STANCE_RECKLESS)

#: Fraction of max HP at which each stance's nerve breaks (0.0 = never).
STANCE_FLEE_AT_HP = {
    STANCE_FLIGHTY: 0.5,
    STANCE_CAUTIOUS: 0.35,
    STANCE_NORMAL: 0.2,
    STANCE_STEADFAST: 0.0,
    STANCE_FEARLESS: 0.0,
    STANCE_RECKLESS: 0.0,
}

#: Stances that can also break when badly outnumbered (the others stand).
OUTNUMBERED_PRONE_STANCES = (STANCE_FLIGHTY, STANCE_CAUTIOUS, STANCE_NORMAL)

#: Creature types that have no nerve to break.
FEARLESS_CREATURE_TYPES = ('undead', 'construct')

# Explicit ``combat_personality`` tags -> stance.
TAG_STANCES: Dict[str, str] = {
    'coward': STANCE_FLIGHTY, 'cowardly': STANCE_FLIGHTY, 'craven': STANCE_FLIGHTY,
    'timid': STANCE_FLIGHTY, 'skittish': STANCE_FLIGHTY, 'meek': STANCE_FLIGHTY,
    'jumpy': STANCE_FLIGHTY, 'neurotic': STANCE_FLIGHTY, 'easily frightened': STANCE_FLIGHTY,
    'panicky': STANCE_FLIGHTY, 'panic-prone': STANCE_FLIGHTY, 'spineless': STANCE_FLIGHTY,
    'wary': STANCE_CAUTIOUS, 'cautious': STANCE_CAUTIOUS, 'circumspect': STANCE_CAUTIOUS,
    'paranoid': STANCE_CAUTIOUS, 'cunning': STANCE_CAUTIOUS, 'devious': STANCE_CAUTIOUS,
    'sneaky': STANCE_CAUTIOUS, 'skulking': STANCE_CAUTIOUS, 'ambusher': STANCE_CAUTIOUS,
    'guerrilla': STANCE_CAUTIOUS, 'hit-and-run': STANCE_CAUTIOUS, 'hit and run': STANCE_CAUTIOUS,
    'brave': STANCE_STEADFAST, 'bold': STANCE_STEADFAST, 'steadfast': STANCE_STEADFAST,
    'stalwart': STANCE_STEADFAST, 'courageous': STANCE_STEADFAST, 'valor': STANCE_STEADFAST,
    'honorable': STANCE_STEADFAST, 'honourable': STANCE_STEADFAST, 'dutiful': STANCE_STEADFAST,
    'disciplined': STANCE_STEADFAST, 'protective': STANCE_STEADFAST, 'loyal': STANCE_STEADFAST,
    'fearless': STANCE_FEARLESS, 'fearless to the death': STANCE_FEARLESS,
    'fanatic': STANCE_FEARLESS, 'zealot': STANCE_FEARLESS, 'frenzied': STANCE_FEARLESS,
    'berserk': STANCE_RECKLESS, 'reckless': STANCE_RECKLESS, 'savage': STANCE_RECKLESS,
    'ferocious': STANCE_RECKLESS, 'bloodthirsty': STANCE_RECKLESS, 'murderous': STANCE_RECKLESS,
    'ruthless': STANCE_RECKLESS, 'predatory': STANCE_RECKLESS, 'relentless': STANCE_RECKLESS,
    'aggressive': STANCE_RECKLESS,
}

#: Free-text phrases that identify a stance (matched over the profile fields).
_PHRASE_STANCES: Tuple[Tuple[str, str], ...] = (
    ('fights to the death', STANCE_FEARLESS),
    ('fight to the death', STANCE_FEARLESS),
    ('to the last', STANCE_FEARLESS),
    ('never retreats', STANCE_FEARLESS),
    ('never retreat', STANCE_FEARLESS),
    ('never runs away', STANCE_FEARLESS),
    ('never flees', STANCE_FEARLESS),
    ('stands and fights', STANCE_FEARLESS),
    ('no self-preservation', STANCE_FEARLESS),
    ('no self preservation', STANCE_FEARLESS),
    ('runs at the first', STANCE_FLIGHTY),
    ('flees at the first', STANCE_FLIGHTY),
    ('flee at the first', STANCE_FLIGHTY),
    ('fleeing at the first', STANCE_FLIGHTY),
    ('runs from any fight', STANCE_FLIGHTY),
    ('runs from any encounter', STANCE_FLIGHTY),
    ('run from any fight', STANCE_FLIGHTY),
    ('runs from a fight', STANCE_FLIGHTY),
    ('runs away from any', STANCE_FLIGHTY),
    ('runs away at the first', STANCE_FLIGHTY),
    ('flees when hard pressed', STANCE_CAUTIOUS),
    ('fights dirty', STANCE_CAUTIOUS),
    ('hit and run', STANCE_CAUTIOUS),
    ('hit-and-run', STANCE_CAUTIOUS),
    ('avoids direct combat', STANCE_CAUTIOUS),
    ('avoids a fair fight', STANCE_CAUTIOUS),
    ('attacks only the weak', STANCE_CAUTIOUS),
    ('charging in headlong', STANCE_RECKLESS),
    ('charges in headlong', STANCE_RECKLESS),
    ('sees red', STANCE_RECKLESS),
    ('loves a fight', STANCE_RECKLESS),
    ('eager for combat', STANCE_RECKLESS),
)

#: Profile keys scanned when inferring a disposition (highest signal first).
_DISPOSITION_FIELDS = (
    'combat_personality',
    'personality_traits',
    'flaws',
    'ideals',
    'bonds',
    'backstory',
    'description',
)

#: Where authored weaknesses live.
_WEAKNESS_FIELDS = ('combat_weaknesses', 'combat_flaw', 'combat_vulnerabilities')

#: How much profile prose is scanned when inferring a disposition.
MAX_PROFILE_SCAN = 3000

# One alternation per keyword set (longest first, so "cowardly" wins over
# "coward") instead of a regex per tag for every JEV question.
def _alternation(words: Iterable[str]) -> 're.Pattern':
    return re.compile('|'.join(re.escape(w) for w in sorted(words, key=len, reverse=True)))


_TAG_RE = _alternation(TAG_STANCES)
_PHRASE_RE = _alternation(phrase for phrase, _stance in _PHRASE_STANCES)


def _match_stance(text: str) -> Tuple[Optional[str], Optional[str]]:
    """First stance keyword in ``text`` as ``(stance, label)``."""
    if not text:
        return None, None
    tag = _TAG_RE.search(text)
    phrase = _PHRASE_RE.search(text)
    if tag and (not phrase or tag.start() <= phrase.start()):
        return TAG_STANCES[tag.group(0)], tag.group(0)
    if phrase:
        for name, stance in _PHRASE_STANCES:
            if name == phrase.group(0):
                return stance, name
    return None, None


MAX_PERSONA_LINE = 260

#: Movement intent the morale system asks the executor for.
MORALE_MOVE_INTENT = 'retreat'


def _props(entity) -> Dict[str, Any]:
    props = getattr(entity, 'properties', None)
    return props if isinstance(props, dict) else {}


def _text_of(value: Any) -> str:
    """Flatten a YAML string/list/dict into one lowercase search string."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, (list, tuple)):
        return ' ; '.join(_text_of(v) for v in value)
    if isinstance(value, dict):
        return ' ; '.join(_text_of(v) for v in value.values())
    return str(value).lower()


def _text_list(value: Any) -> List[str]:
    """A YAML string/list field as authored (display) strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if isinstance(item, dict):
                item = item.get('description') or item.get('text') or item.get('name')
            text = str(item or '').strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def _creature_types(entity) -> List[str]:
    found: List[str] = []
    try:
        if not getattr(entity, 'npc', lambda: True)():
            found.append('humanoid')
    except Exception:
        pass
    props = _props(entity)
    for key in ('kind', 'race', 'creature_type'):
        value = props.get(key)
        if isinstance(value, (list, tuple)):
            found.extend(str(v).lower() for v in value)
        elif value:
            found.append(str(value).lower())
    return found


def is_fearless_creature(entity) -> bool:
    """Undead, constructs and ``fearless`` creatures have no nerve to break."""
    if any(t in FEARLESS_CREATURE_TYPES for t in _creature_types(entity)):
        return True
    for checker in ('class_feature', 'has_class_feature'):
        fn = getattr(entity, checker, None)
        if callable(fn):
            try:
                if fn('fearless'):
                    return True
            except Exception:
                continue
    if 'fearless' in (_props(entity).get('features') or []):
        return True
    return False


def disposition(entity) -> Dict[str, Any]:
    """This creature's battle disposition.

    Keys: ``stance``, ``flee_at_hp`` (fraction of max HP, 0 = never),
    ``flee_when_outnumbered``, ``never_flee``, ``labels`` (the personality tags
    that matched) and ``authored`` (True when the creature's YAML said so).
    """
    props = _props(entity)
    stance = None
    labels: List[str] = []
    authored = False

    morale = props.get('morale')
    if isinstance(morale, dict):
        explicit = str(morale.get('stance') or '').strip().lower()
        if explicit in STANCES:
            stance = explicit
            authored = True
        tag_text = _text_of(props.get('combat_personality'))
    else:
        tag_text = _text_of(props.get('combat_personality'))

    # 1. explicit combat_personality tags (tags or prose in that field)
    if stance is None and tag_text:
        stance, label = _match_stance(tag_text)
        if label:
            labels.append(label)
            authored = True
    # 2. profile prose keywords (cowardly / brave / reckless wording)
    if stance is None:
        for key in _DISPOSITION_FIELDS:
            if key == 'combat_personality':
                continue
            stance, label = _match_stance(_text_of(props.get(key))[:MAX_PROFILE_SCAN])
            if label:
                labels.append(label)
                break
    if stance is None:
        stance = STANCE_NORMAL

    never_flee = bool(is_fearless_creature(entity))
    if isinstance(morale, dict):
        if morale.get('never_flee') or morale.get('ignores_self_preservation'):
            never_flee = True
            authored = True
    if never_flee and not authored:
        # Undead, constructs and fearless creatures have no nerve to break;
        # unless the author named a stance, treat them as fearless.
        stance = STANCE_FEARLESS

    flee_at = STANCE_FLEE_AT_HP.get(stance, 0.2)
    if isinstance(morale, dict):
        for key in ('flee_at_hp', 'flee_hp_fraction', 'break_at_hp'):
            raw = morale.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value > 1:      # accept a percentage too
                value /= 100.0
            flee_at = max(0.0, min(1.0, value))
            authored = True
            break
    if never_flee:
        flee_at = 0.0

    outnumbered = stance in OUTNUMBERED_PRONE_STANCES
    if isinstance(morale, dict) and 'flee_when_outnumbered' in morale:
        outnumbered = bool(morale.get('flee_when_outnumbered'))
        authored = True
    if never_flee:
        outnumbered = False

    return {
        'stance': stance,
        'flee_at_hp': flee_at,
        'flee_when_outnumbered': outnumbered,
        'never_flee': never_flee,
        'labels': labels,
        'authored': authored,
    }


# --------------------------------------------------------------------------- #
# Morale                                                                      #
# --------------------------------------------------------------------------- #

def _hp_fraction(entity) -> Optional[float]:
    try:
        current = entity.hp()
        maximum = entity.max_hp() or 0
        if maximum <= 0:
            return None
        return max(0.0, float(current) / float(maximum))
    except Exception:
        return None


def visible_threats(battle, entity) -> List[Any]:
    """Conscious enemies this creature can currently see."""
    if battle is None or entity is None:
        return []
    try:
        return [e for e in battle.opponents_of(entity)
                if not e.dead() and battle.can_see(entity, e)]
    except Exception:
        return []


def _allies_alive(battle, entity) -> int:
    try:
        return sum(1 for a in battle.allies_of(entity) if a is not entity and not a.dead())
    except Exception:
        return 0


def threat_ratio(battle, entity) -> float:
    """Enemies in sight per living ally (at least 1)."""
    threats = len(visible_threats(battle, entity))
    if threats <= 0:
        return 0.0
    allies = _allies_alive(battle, entity)
    return threats / float(allies + 1)


def morale_broken(battle, entity) -> bool:
    """Has this creature's nerve broken? Latched for the rest of the fight."""
    if battle is None or entity is None:
        return False
    disp = disposition(entity)
    if disp['never_flee']:
        return False
    try:
        state = battle.entity_state_for(entity)
    except Exception:
        return False
    if state is None:
        return False
    if state.get(MORALE_STATE_KEY):
        return True
    threats = visible_threats(battle, entity)
    if not threats:
        return False
    fraction = _hp_fraction(entity)
    broken = False
    reason = None
    if fraction is not None and disp['flee_at_hp'] > 0 and fraction <= disp['flee_at_hp']:
        broken = True
        reason = 'wounded'
    elif disp['flee_when_outnumbered'] and threat_ratio(battle, entity) >= 2.0:
        broken = True
        reason = 'outnumbered'
    if not broken:
        return False
    state[MORALE_STATE_KEY] = True
    _log_morale_break(battle, entity, reason)
    return True


def _log_morale_break(battle, entity, reason: Optional[str]) -> None:
    """One combat-log line the moment a creature's nerve breaks."""
    em = getattr(battle, 'event_manager', None)
    if em is None:
        return
    message = f"{getattr(entity, 'name', 'It')} loses its nerve and looks for a way out"
    try:
        em.received_event({
            'source': entity,
            'event': 'morale_break',
            'battle': battle,
            'message': message,
            'reason': reason,
        })
    except Exception as exc:  # pragma: no cover - logging must not break combat
        logger.debug("[morale] could not log morale break: %s", exc)


def morale_directive(battle, entity) -> Optional[str]:
    """The movement intent a broken creature should follow, else ``None``."""
    if morale_broken(battle, entity):
        return MORALE_MOVE_INTENT
    return None


def flee_threat(battle, entity) -> Optional[Any]:
    """Who this creature would run from: the nearest threat in sight."""
    threats = visible_threats(battle, entity)
    if not threats:
        return None
    try:
        battle_map = battle.map_for(entity)
    except Exception:
        battle_map = None

    def distance(other) -> float:
        if battle_map is None:
            return 0.0
        try:
            return battle_map.distance(entity, other)
        except Exception:
            return 0.0

    return min(threats, key=distance)


# --------------------------------------------------------------------------- #
# Prompt blocks                                                               #
# --------------------------------------------------------------------------- #

_STANCE_LINES = {
    STANCE_FLIGHTY: (
        "{name} is a coward: its own safety matters more than the fight. When "
        "hurt or outnumbered, its orders must be to break off and run (Dash "
        "away, Disengage, hide behind cover) rather than trade blows."
    ),
    STANCE_CAUTIOUS: (
        "{name} fights cautiously: it prefers ambush, range and cover, avoids "
        "a fair fight, and slips away when the odds turn against it."
    ),
    STANCE_NORMAL: (
        "{name} fights like any sane soldier: it keeps fighting while the "
        "fight is winnable and considers retreat when near death."
    ),
    STANCE_STEADFAST: (
        "{name} is brave and holds its ground: it does not run from danger, "
        "and stays in the fight to protect allies or finish the job."
    ),
    STANCE_FEARLESS: (
        "{name} is fearless: it never retreats, never surrenders and fights "
        "until it drops. Never order it to flee."
    ),
    STANCE_RECKLESS: (
        "{name} is reckless and aggressive: it charges the nearest foe, takes "
        "risks and ignores its own wounds. Never order it to retreat."
    ),
}


def weakness_lines(entity) -> List[str]:
    """Authored weaknesses plus damage vulnerabilities (what the AI fears)."""
    props = _props(entity)
    out: List[str] = []
    for key in _WEAKNESS_FIELDS:
        for text in _text_list(props.get(key)):
            out.append(text)
    vulns = list(getattr(entity, 'damage_vulnerabilities', None) or [])
    if not vulns:
        raw = props.get('damage_vulnerabilities') or props.get('vulnerabilities') or []
        vulns = [str(v) for v in raw] if isinstance(raw, (list, tuple)) else []
    if vulns:
        out.append("vulnerable to " + ", ".join(sorted({v.lower() for v in vulns})) + " damage")
    return out


def persona_lines(battle, entity) -> List[str]:
    """Battle-psychology lines for any AI prompt (JEV state, LLM prompt,
    hybrid strategist plan). Empty when the creature has no notable psyche."""
    lines: List[str] = []
    try:
        disp = disposition(entity)
    except Exception:
        disp = None
    if disp:
        stance = disp['stance']
        line = _STANCE_LINES.get(stance, '').format(
            name=getattr(entity, 'name', 'It') or 'It')
        if line:
            lines.append(line)
        if disp['labels']:
            lines.append("personality: " + ", ".join(sorted(set(disp['labels']))))
        if disp['flee_at_hp'] > 0:
            pct = int(round(disp['flee_at_hp'] * 100))
            lines.append(
                f"nerve: {getattr(entity, 'name', 'It')} breaks and runs at or below "
                f"{pct}% of its hit points"
                + (", or when badly outnumbered" if disp['flee_when_outnumbered'] else "")
                + "."
            )
    state_broken = False
    try:
        state = battle.entity_state_for(entity) if battle is not None else None
        state_broken = bool(state and state.get(MORALE_STATE_KEY))
    except Exception:
        state_broken = False
    if state_broken:
        lines.append("its nerve has ALREADY broken this fight: this turn is about "
                     "getting away (Dash, Disengage, hide), not about winning.")
    for text in weakness_lines(entity):
        lines.append(f"weakness: {text}")
    return [ln[:MAX_PERSONA_LINE] for ln in lines if ln]
