"""Helpers for monster legendary actions (SRD "Legendary Actions").

NPC YAML lists options under ``legendary_actions``. Each option is either an
attack (``type: melee_attack`` / ``ranged_attack``, same shape as ``actions``)
or a movement option (``type: move``). Optional keys:

- ``cost`` – legendary actions spent (default 1), e.g. ``cost: 2`` for
  "Bite (Costs 2 Actions)".
- ``provokes_opportunity_attacks`` – only for ``type: move``; defaults to
  false ("moves up to its speed without provoking opportunity attacks").

The pool size per round comes from ``legendary_action_count`` (default 3)
and refills at the start of the creature's turn.
"""

DEFAULT_LEGENDARY_ACTION_COUNT = 3


def legendary_action_cost(option):
    if not isinstance(option, dict):
        return 1
    try:
        return max(1, int(option.get('cost', 1) or 1))
    except (TypeError, ValueError):
        return 1


def is_legendary_move(option):
    return isinstance(option, dict) and str(option.get('type', '')).lower() == 'move'


def legendary_pool_size(entity):
    properties = getattr(entity, 'properties', None) or {}
    if not properties.get('legendary_actions'):
        return 0
    try:
        return max(0, int(properties.get('legendary_action_count', DEFAULT_LEGENDARY_ACTION_COUNT)))
    except (TypeError, ValueError):
        return DEFAULT_LEGENDARY_ACTION_COUNT


def mark_legendary_move(action, option):
    """Flag a ``MoveAction`` as the legendary ``type: move`` ``option``."""
    action.legendary_action = True
    action.legendary_cost = legendary_action_cost(option)
    action.ignore_opportunity_attacks = not option.get('provokes_opportunity_attacks', False)
    return action


def has_legendary_choice(entity, battle):
    """True when the creature can spend a legendary action right now."""
    if (entity.total_legendary_actions(battle) or 0) <= 0:
        return False
    if hasattr(entity, 'legendary_move_options') and entity.legendary_move_options(battle):
        return True
    generate = getattr(entity, 'generate_npc_attack_actions', None)
    if not callable(generate):
        return False
    return bool(generate(battle, legendary_actions=True, auto_target=True))


def prepare_legendary_phase_action(entity, battle, action):
    """Convert a manually chosen action into the matching legendary action.

    Used while ``battle.legendary_phase`` is open for ``entity``. Returns
    an error message when ``action`` is not a legal legendary action, else
    ``None`` (``action`` is updated in place).
    """
    from natural20.actions.attack_action import AttackAction
    from natural20.actions.move_action import MoveAction

    pool = entity.total_legendary_actions(battle) or 0
    if isinstance(action, MoveAction):
        options = entity.legendary_move_options(battle) if hasattr(entity, 'legendary_move_options') else []
        if not options:
            return f"{entity.label()} has no legendary move available."
        mark_legendary_move(action, min(options, key=legendary_action_cost))
        return None
    if isinstance(action, AttackAction):
        chosen = getattr(action, 'npc_action', None) or {}
        name = chosen.get('name') if isinstance(chosen, dict) else None
        for option in getattr(entity, 'legendary_actions', None) or []:
            if is_legendary_move(option) or option.get('name') != name:
                continue
            if pool < legendary_action_cost(option):
                return f"Not enough legendary actions for {name}."
            action.npc_action = option
            action.legendary_action = True
            return None
        return f"{name or 'That attack'} is not a legendary action."
    return "Only legendary actions can be taken during a legendary action phase."
