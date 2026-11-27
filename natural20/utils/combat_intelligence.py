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

The same tiers cap how much *planning* a creature is credited with, which is
what gates the hybrid LLM strategist (``natural20.llm_controller.
HybridStrategistController``) and the movement intents its executor will
honour: see ``strategist_policy`` and ``allowed_move_intents`` below. A wolf
(INT 3) never gets a step-by-step battle plan; a mastermind gets the full one.
Override with the YAML property ``strategist: auto|always|off``.
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
# What the creature can PLAN (hybrid LLM strategist + move intents)           #
# --------------------------------------------------------------------------- #

# Per-tier planner capability, used by ``HybridStrategistController``:
#   plan            - does the creature get a generative turn plan at all
#   max_lines       - hard cap on the plan text (lines)
#   max_chars       - hard cap on the plan text (characters)
#   steps           - how many numbered concrete steps to order
#   move_tags       - MOVE: intents (``natural20.utils.jev_decision`` tags)
#                     the creature can understand and follow
#   reactions       - may the plan spend the reaction on other creatures' turns
#   guidance        - the persona line the planner is told to write in character
_STRATEGIST_POLICY = {
    'instinct': {
        'plan': False, 'max_lines': 2, 'max_chars': 220, 'steps': 0,
        'move_tags': (), 'reactions': False,
        'guidance': (
            "{name} is a beast of pure instinct (INT {score}). It cannot plan: "
            "order at most ONE blunt thing (maul the closest foe / run), never "
            "mention spell slots, cover, flanking, kiting, feints, healing or "
            "reactions, and use no tactical vocabulary at all."
        ),
    },
    'simple': {
        'plan': True, 'max_lines': 4, 'max_chars': 400, 'steps': 1,
        'move_tags': ('engage', 'retreat', 'hold'), 'reactions': False,
        'guidance': (
            "{name} is dim-witted (INT {score}). Order at most {steps} simple "
            "step: attack the nearest foe or whoever hurt it, gang up on a foe "
            "others already fight, or fall back when badly hurt. No feints, no "
            "reasoning about spellcasters, concentration, spell slots, cover, "
            "flanking or reactions."
        ),
    },
    'tactical': {
        'plan': True, 'max_lines': 10, 'max_chars': 900, 'steps': 3,
        'move_tags': ('engage', 'retreat', 'range', 'hide', 'hold'),
        'reactions': True,
        'guidance': (
            "{name} is a capable fighter (INT {score}). Give {steps} sound "
            "steps: focus fire, protect wounded allies, use cover, keep to its "
            "own strengths. Do not attempt subtle multi-turn deception."
        ),
    },
    'mastermind': {
        'plan': True, 'max_lines': 16, 'max_chars': 1400, 'steps': 6,
        'move_tags': ('engage', 'retreat', 'range', 'hide', 'hold'),
        'reactions': True,
        'guidance': (
            "{name} is a brilliant tactician (INT {score}). Plan ahead up to "
            "{steps} steps: neutralize healers and spellcasters, break "
            "concentration, exploit vulnerabilities and overheard enemy plans, "
            "and set up reactions for the other side's turns."
        ),
    },
}

#: Movement intents a creature of each tier can act on (JEV ``MOVE:`` tags).
STRATEGIST_MOVE_TAGS = {tier: cfg['move_tags'] for tier, cfg in _STRATEGIST_POLICY.items()}

#: ``strategist:`` YAML/override values that force planning on or off.
STRATEGIST_ALWAYS = ('always', 'force', 'forced', 'on', 'yes')
STRATEGIST_OFF = ('off', 'never', 'none', 'disable', 'disabled', 'no')


def _entity_props(entity) -> dict:
    props = getattr(entity, 'properties', None)
    return props if isinstance(props, dict) else {}


def strategist_mode(entity) -> str:
    """The creature's ``strategist:`` YAML override: ``auto|always|off``."""
    value = str(_entity_props(entity).get('strategist') or '').strip().lower()
    if value in STRATEGIST_ALWAYS:
        return 'always'
    if value in STRATEGIST_OFF:
        return 'off'
    return 'auto'


def strategist_policy(entity, mode: Optional[str] = None) -> dict:
    """How much battle planning this creature deserves.

    ``mode`` (``auto|always|off``) overrides the creature's own YAML
    ``strategist:`` key; ``auto`` follows its intelligence tier. The returned
    dict carries ``tier``, ``plan``, ``max_lines``, ``max_chars``, ``steps``,
    ``move_tags``, ``reactions`` and a ``guidance`` line for the prompt.
    """
    tier = tactics_tier(entity)
    policy = dict(_STRATEGIST_POLICY[tier])
    explicit = str(mode or '').strip().lower()
    if explicit in STRATEGIST_ALWAYS:
        mode_final = 'always'
    elif explicit in STRATEGIST_OFF:
        mode_final = 'off'
    else:
        mode_final = strategist_mode(entity)
    if mode_final == 'always':
        policy['plan'] = True
    elif mode_final == 'off':
        policy['plan'] = False
    policy['mode'] = mode_final
    policy['tier'] = tier
    policy['move_tags'] = tuple(STRATEGIST_MOVE_TAGS[tier])
    policy['guidance'] = policy['guidance'].format(
        name=getattr(entity, 'name', 'It') or 'It',
        score=intelligence_score(entity),
        steps=policy['steps'],
    )
    return policy


def can_plan(entity, mode: Optional[str] = None) -> bool:
    """Whether a generative strategist should write this creature's turn plan."""
    return bool(strategist_policy(entity, mode)['plan'])


def allowed_move_intents(entity, mode: Optional[str] = None) -> tuple:
    """The ``MOVE:`` intent tags this creature's wits let it follow."""
    return strategist_policy(entity, mode)['move_tags']

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
