"""Intelligence-scaled tactics for AI-controlled combatants.

Following the DMG's advice to play creatures according to their
Intelligence, every AI-driven combatant (LLM, JEV, and the controllers'
callout logic) gets a *tactics tier* derived from its INT score:

=============  =====  ==========================================================
tier           INT    behaviour
=============  =====  ==========================================================
``instinct``   1-3    Fights on instinct: attacks the nearest threat or whoever
                      just hurt it, never coordinates, ignores callouts.
``simple``     4-7    Simple tactics: ganging up, fleeing when badly hurt; only
                      short, simple callouts (focus / help / heal / retreat).
``tactical``   8-13   Sound tactics: focus fire, protects allies, full callouts.
``mastermind`` 14+    Plans ahead: targets casters and concentration, exploits
                      overheard enemy callouts, speaks in languages enemies lack.
=============  =====  ==========================================================

Override per creature with the NPC/character YAML property
``tactics: instinct|simple|tactical|mastermind``.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

TIERS = ('instinct', 'simple', 'tactical', 'mastermind')

SIMPLE_CALLOUT_KINDS = ('focus', 'help', 'heal', 'retreat', 'regroup', 'taunt', 'say')
SIMPLE_MAX_WORDS = 6

_GUIDANCE = {
    'instinct': (
        "You are a creature of instinct with almost no intellect (INT {score}). You do not plan, "
        "coordinate, or weigh spell slots or concentration. Attack the closest enemy or whoever just hurt you; "
        "flee only from overwhelming pain. Ignore anything said around you."
    ),
    'simple': (
        "You are dim-witted (INT {score}). Use only simple tactics: gang up on a foe allies are already "
        "fighting, go after whoever hurt you, run when badly wounded. You do not reason about spellcasting, "
        "concentration, or clever positioning."
    ),
    'tactical': (
        "You are a capable fighter (INT {score}). Use sound tactics: focus fire, protect wounded allies, "
        "use cover, and follow allies' callouts when they make sense."
    ),
    'mastermind': (
        "You are a brilliant tactician (INT {score}). Plan ahead: neutralize healers and spellcasters first, "
        "break concentration, exploit vulnerabilities, and use any enemy callouts you overheard against them."
    ),
}


def intelligence_score(entity) -> int:
    for getter in ('ability_score_int',):
        fn = getattr(entity, getter, None)
        if callable(fn):
            try:
                val = fn()
                if val is not None:
                    return int(val)
            except Exception:
                pass
    scores = getattr(entity, 'ability_scores', None) or {}
    try:
        return int(scores.get('int', 10) or 10)
    except (TypeError, ValueError):
        return 10


def tactics_tier(entity) -> str:
    props = getattr(entity, 'properties', None) or {}
    override = str(props.get('tactics') or '').strip().lower() if isinstance(props, dict) else ''
    if override in TIERS:
        return override
    score = intelligence_score(entity)
    if score <= 3:
        return 'instinct'
    if score <= 7:
        return 'simple'
    if score <= 13:
        return 'tactical'
    return 'mastermind'


def tier_rank(entity) -> int:
    return TIERS.index(tactics_tier(entity))


def guidance(entity) -> str:
    return _GUIDANCE[tactics_tier(entity)].format(score=intelligence_score(entity))


# --------------------------------------------------------------------------- #
# Communication limits                                                        #
# --------------------------------------------------------------------------- #

def can_coordinate(entity) -> bool:
    """Instinct-tier creatures never issue tactical callouts."""
    return tactics_tier(entity) != 'instinct'


def allowed_callout_kind(entity, kind: str) -> bool:
    tier = tactics_tier(entity)
    if tier == 'instinct':
        return False
    if tier == 'simple':
        return kind in SIMPLE_CALLOUT_KINDS
    return True


def max_callout_words(entity, cap: int) -> int:
    if tactics_tier(entity) == 'simple':
        return min(cap, SIMPLE_MAX_WORDS)
    return cap


def comprehends_callout(entity, entry: dict) -> bool:
    """Whether the listener can act on a heard callout given its wits."""
    tier = tactics_tier(entity)
    if tier == 'instinct':
        return False
    if tier == 'simple':
        return entry.get('kind') in SIMPLE_CALLOUT_KINDS
    return True


def exploits_overheard_enemies(entity) -> bool:
    return tactics_tier(entity) in ('tactical', 'mastermind')


# --------------------------------------------------------------------------- #
# Instinctive target selection                                                #
# --------------------------------------------------------------------------- #

def _targets(action) -> List[Any]:
    t = getattr(action, 'target', None)
    if t is None:
        return []
    if isinstance(t, (list, tuple)):
        return [x for x in t if hasattr(x, 'entity_uid')]
    return [t] if hasattr(t, 'entity_uid') else []


def _distance_ft(battle, a, b) -> Optional[float]:
    try:
        m = battle.map_for(a)
        return m.distance(a, b) * m.feet_per_grid
    except Exception:
        return None


def last_attacker(battle, entity):
    """Most recent opponent whose logged action targeted *entity*."""
    for action in reversed(list(getattr(battle, 'battle_log', None) or [])):
        source = getattr(action, 'source', None)
        if source is None or source is entity:
            continue
        if entity not in _targets(action):
            continue
        try:
            if battle.opposing(entity, source) and not source.dead():
                return source
        except Exception:
            continue
    return None


def instinct_targets(battle, entity) -> List[Any]:
    """Enemies an instinct-tier creature would go after: the nearest ones
    (within 5 ft of the closest) plus whoever last attacked it."""
    try:
        enemies = [e for e in battle.opponents_of(entity)
                   if not e.dead() and battle.can_see(entity, e)]
    except Exception:
        return []
    dists = [(d, e) for e in enemies if (d := _distance_ft(battle, entity, e)) is not None]
    allowed = []
    if dists:
        nearest = min(d for d, _ in dists)
        allowed = [e for d, e in dists if d <= nearest + 5]
    attacker = last_attacker(battle, entity)
    if attacker is not None and attacker not in allowed:
        allowed.append(attacker)
    return allowed


def filter_actions(battle, entity, actions: Iterable[Any], target_of=None) -> List[Any]:
    """Drop hostile-targeted actions an instinct-tier creature would not pick.

    Non-hostile actions are kept; if filtering would remove everything the
    original list is returned. ``target_of`` maps an item to its action (for
    lists of tuples such as JEV leaves).
    """
    items = list(actions or [])
    if battle is None or tactics_tier(entity) != 'instinct':
        return items
    allowed = instinct_targets(battle, entity)
    if not allowed:
        return items
    allowed_ids = {id(e) for e in allowed}

    def keep(item):
        action = target_of(item) if target_of else item
        hostile = []
        for t in _targets(action):
            try:
                if battle.opposing(entity, t):
                    hostile.append(t)
            except Exception:
                continue
        return not hostile or any(id(t) in allowed_ids for t in hostile)

    kept = [i for i in items if keep(i)]
    return kept or items
