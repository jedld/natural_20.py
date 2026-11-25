"""Player instruction following via the Jev "System One" decision model.

Two related, provider-agnostic helpers live here:

``InstructionPlanner``
    Executes a free-text player instruction **step by step**. Each step
    re-derives the entity's legal leaf actions (the same flattened option
    space :class:`natural20.utils.jev_decision.JevActionPlanner` builds for
    NPC AI), adds the entity's current entity context, what the instruction
    has already done, and a mandatory ``stop`` leaf, then asks the decision
    model for the single option that best matches the instruction. The
    webapp commits the returned action, refreshes, and asks again until the
    model chooses ``stop`` (nothing left that fits), an explicit end-turn
    leaf (only offered when the player asked to end the turn), or a
    ``ready`` leaf (the instruction describes an out-of-turn Ready action).

``parse_player_instruction``
    The System One counterpart of the generative-LLM Ready/Hold parser: one
    state block plus two flat Choice questions (trigger event, prepared
    action) classify the player's free text into the normalized
    ``trigger`` / ``action_spec`` structures consumed by
    :class:`natural20.actions.ready_action.ReadyAction`. Two Choice calls
    cost a fraction of a prose generation and cannot invent weapons, spells
    or triggers that the entity does not have - every option is enumerated
    from the entity's actual sheet.

Like the planner, this module only requires a provider object exposing
``decide_action(state, options) -> dict|None`` (``JevProvider`` satisfies
this) and returns ``None`` on any failure so callers can fall back.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from natural20.utils.jev_decision import (
    JevActionPlanner,
    _fit_state,
)

logger = logging.getLogger(__name__)

# Steps the webapp may take for one instruction before giving up.
DEFAULT_INSTRUCTION_BUDGET = 8
# How many completed steps are echoed back into the decision state.
MAX_INSTRUCTION_HISTORY = 12
# Ready (System One) question caps.
MAX_READY_TRIGGERS = 12
MAX_READY_ACTIONS = 40


# --------------------------------------------------------------------------- #
# Sentinels: planner "leaves" that are not real actions but control the loop.
# The webapp recognizes them via ``is_instruction_sentinel`` and never
# commits them through the normal action path.
# --------------------------------------------------------------------------- #

class InstructionStop:
    """No remaining action matches the instruction: stop and hand back."""


class InstructionEndTurn:
    """The player asked to end the turn: end it."""


class InstructionReady:
    """The instruction describes an out-of-turn Ready (hold) action."""


_SENTINELS = (InstructionStop, InstructionEndTurn, InstructionReady)


def is_instruction_sentinel(action: Any) -> bool:
    """True when ``action`` is one of the loop-control sentinels."""
    return isinstance(action, _SENTINELS)


def provider_can_follow_instructions(provider: Any) -> bool:
    """True when ``provider`` can answer System One Choice questions."""
    return bool(
        provider is not None
        and getattr(provider, 'is_available', False)
        and callable(getattr(provider, 'decide_action', None))
    )


# --------------------------------------------------------------------------- #
# Instruction planner
# --------------------------------------------------------------------------- #

class InstructionPlanner(JevActionPlanner):
    """One step of a player instruction per :meth:`select_step` call.

    Unlike the AI planner, movement leaves stay in the menu (the human's
    ``move_for`` hook does not run), a ``ready`` leaf is offered while it is
    legal in combat, and the always-present pass leaf becomes an explicit
    ``stop`` sentinel unless the player's instruction mentions ending the
    turn - in which case both ``stop`` and ``end turn`` are offered.
    """

    def __init__(self, provider, entity, instruction: str,
                 done: Optional[List[str]] = None):
        super().__init__(provider)
        self.provider = provider
        self.entity = entity
        self.instruction = (instruction or '').strip()
        self.done = list(done or [])

    # -- one step ----------------------------------------------------------- #

    def select_step(self, battle, available_actions: Optional[List] = None
                    ) -> Tuple[Any, Optional[str]]:
        """Pick the leaf that best matches the instruction.

        Returns ``(action_or_sentinel, description)``. ``action`` is a
        fully-built Action the caller can commit as-is, or one of
        :class:`InstructionStop` / :class:`InstructionEndTurn` /
        :class:`InstructionReady`. ``description`` is the human-readable
        option text (also what the caller should show as progress).
        """
        try:
            if not provider_can_follow_instructions(self.provider):
                return InstructionStop(), "no decision model available"
            if not self.instruction:
                return InstructionStop(), "no instruction"
            entity = self.entity
            if getattr(entity, 'incapacitated', lambda: False)():
                return InstructionStop(), "the creature cannot act"

            self._battle = battle
            self._entity = entity
            self._map = self._resolve_map(battle, entity)
            self._session = getattr(battle, 'session', None) or \
                getattr(entity, 'session', None)
            self._decisions = 0
            self._names = self._display_names(battle, entity)
            self._state = self._instruction_state(battle, entity)

            leaves = self._collect_leaves(available_actions)
            leaves = self._finalize_instruction_leaves(leaves, battle, entity)
            descs = [d for _, _, d in leaves]

            if len(leaves) == 1:
                # Nothing but the stop sentinel survived pruning.
                return self._pop_sentinel(leaves[0], descs)

            idx = self._decide(self._state, descs)
            if idx is None:
                return InstructionStop(), None
            action, desc = leaves[idx][1], descs[idx]
            if not is_instruction_sentinel(action):
                action = self._enrich(battle, entity, action)
                self.done.append(desc)
            logger.debug("[InstrFollow] %s chose %r",
                         getattr(entity, 'name', '?'), desc)
            return action, desc
        except Exception as exc:  # never break a player's turn
            logger.debug("[InstrFollow] step failed: %s", exc)
            return InstructionStop(), None

    # -- leaves -------------------------------------------------------------- #

    def _resolve_map(self, battle, entity):
        if battle is not None:
            try:
                return battle.map_for(entity)
            except Exception:
                pass
        session = getattr(entity, 'session', None)
        if session is not None:
            try:
                return session.map_for_entity(entity)
            except Exception:
                pass
            try:
                return session.map_for(entity)
            except Exception:
                pass
        return getattr(entity, 'current_map', None) or getattr(entity, 'map', None)

    def _finalize_instruction_leaves(self, leaves, battle, entity):
        """Replace the pass leaf with the instruction's stop/end/ready set."""
        leaves = [leaf for leaf in leaves if leaf[0] != 'end_turn']

        if battle is not None and self._ready_is_legal(battle, entity):
            leaves.append((
                'ready', InstructionReady(),
                "ready (hold) an action for later \u2014 choose this when the "
                "instruction describes reacting to a trigger out of turn "
                "(e.g. 'if the goblin comes through the door, shoot it')",
            ))

        # The stop sentinel is last and is always present: the model can
        # refuse or finish at any step.
        leaves = [leaf for leaf in leaves if leaf[0] != 'instruction_stop']
        leaves.append((
            'instruction_stop', InstructionStop(),
            "stop (no remaining action matches the player's instruction, or "
            "the instruction is already complete)",
        ))
        if _mentions_end_turn(self.instruction):
            leaves.insert(-1, (
                'instruction_end_turn', InstructionEndTurn(),
                "end the turn now (the player asked to end the turn)",
            ))
        return leaves

    def _ready_is_legal(self, battle, entity) -> bool:
        try:
            from natural20.actions.ready_action import ReadyAction
            return bool(ReadyAction.can(entity, battle))
        except Exception:
            return False

    def _pop_sentinel(self, leaf, descs):
        action, desc = leaf[1], leaf[2]
        if is_instruction_sentinel(action):
            return action, desc
        return InstructionStop(), None

    # -- state --------------------------------------------------------------- #

    def _instruction_state(self, battle, entity) -> str:
        """The normal planner state block, re-tasked for the instruction."""
        base = self._render_state(battle, entity) if battle is not None \
            else self._render_state_no_battle(battle, entity)
        lines = [base]
        block = [f"The player instructed you (their human): {self.instruction!r}"]
        if self.done:
            block.append("already done for this instruction:")
            block.extend(f"- {entry}" for entry in self.done[-MAX_INSTRUCTION_HISTORY:])
        block.append(
            "Task: choose the single option index that best advances the "
            "player's instruction from the actions available right now. "
            "Choose the stop option when nothing left fits or the "
            "instruction is complete. Follow the instruction rather than "
            "your own tactics, but never pick anything unsafe or illegal "
            "for the entity."
        )
        lines.append("\n".join(block))
        return _fit_state(lines)

    def _render_state_no_battle(self, battle, entity) -> str:
        """Compact entity context when no battle is active."""
        m = self._map
        lines = []
        try:
            pos = m.position_of(entity) if m else None
            lines.append(
                f"Entity: {entity.name}; HP {_hp_text(entity)}; pos {pos}; "
                f"speed {entity.speed()} ft (no combat in progress)"
            )
            own = getattr(entity, 'statuses', None)
            if own:
                lines.append("statuses: " + ", ".join(sorted(set(own))))
            from natural20.utils.jev_decision import _actor_sheet_lines
            lines.extend(_actor_sheet_lines(battle, entity))
            if m is not None:
                try:
                    lines.extend(self._render_pov_map(battle, entity, m))
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("[InstrFollow] no-battle state failed: %s", exc)
            lines.append("State unavailable.")
        return _fit_state(lines)


_END_TURN_WORDS = re.compile(r"\b(end|finish|close)\s+(the|your|my|its|this)?\s*turn\b",
                             re.IGNORECASE)


def _mentions_end_turn(instruction: str) -> bool:
    return bool(_END_TURN_WORDS.search(instruction or ''))


def _hp_text(entity) -> str:
    try:
        return f"{int(entity.current_hp or 0)}/{int(entity.max_hp or 0)}"
    except Exception:
        return "?"


def follow_instruction_step(provider, battle, entity, instruction: str,
                           done: Optional[List[str]] = None,
                           available_actions: Optional[List] = None
                           ) -> Tuple[Any, Optional[str]]:
    """One instruction step (see :meth:`InstructionPlanner.select_step`)."""
    planner = InstructionPlanner(provider, entity, instruction, done=done)
    return planner.select_step(battle, available_actions=available_actions)


# --------------------------------------------------------------------------- #
# Ready (Hold) parsing with System One
# --------------------------------------------------------------------------- #

_READY_TRIGGER_OPTIONS: List[Tuple[str, str]] = [
    ('movement', "any creature finishes moving (walks into reach, crosses the room)"),
    ('becomes_visible', "a creature you cannot see right now comes into your line of sight"),
    ('start_of_turn', "a particular creature's turn begins"),
    ('attacked', "you get attacked"),
    ('goes_down', "a creature drops to 0 HP (falls unconscious or dies)"),
    ('on_command', "an ally says a specific command word/phrase"),
    ('object_interaction', "an object is used (a door opens, closes or is unlocked)"),
    ('ally_attacks', "an ally makes an attack"),
]


def parse_player_instruction(provider, battle, entity, description: str,
                            *, weapons: Optional[List[str]] = None,
                            spells: Optional[List[Dict[str, Any]]] = None,
                            items: Optional[List[Dict[str, Any]]] = None,
                            enemies: Optional[List[str]] = None,
                            ) -> Optional[Dict[str, Any]]:
    """Classify a player's free-text Ready description with two Choice calls.

    Returns ``{'trigger': {...}, 'action_spec': {...}}`` using the engine's
    normalized structures, or ``None`` when the model is unavailable or
    fails (the caller should fall back to its rule-based parser). The
    caller still owns 5e legality validation of the chosen action.
    """
    description = (description or '').strip()
    if not description or not provider_can_follow_instructions(provider):
        return None
    try:
        weapons = list(weapons or _known_weapons(entity))
        spells = list(spells or _known_spells(entity))
        items = list(items or _known_items(entity))

        state = _ready_state(battle, entity, description, enemies)

        trig_idx = _ready_decide(
            provider, state,
            "The player readied an action. Which trigger event did they "
            "describe? Choose the option that matches their words.",
            [f"{name}: {meaning}" for name, meaning in _READY_TRIGGER_OPTIONS],
        )
        if trig_idx is None:
            return None
        trigger_event = _READY_TRIGGER_OPTIONS[trig_idx][0]

        action_options = _ready_action_options(weapons, spells, items)
        if not action_options:
            act_kind, act_payload = 'dodge', {}
        else:
            act_idx = _ready_decide(
                provider, state,
                "Which action did the player intend to take when the trigger "
                "happens? Choose an action the entity actually owns; pick the "
                "closest fit to their words.",
                action_options,
            )
            if act_idx is None:
                return None
            act_kind, act_payload = _ready_action_payload(action_options[act_idx])

        from natural20.ready_action import normalize_action_spec, normalize_trigger
        trigger = normalize_trigger({'event': trigger_event,
                                     'description': description})
        spec_raw = {'kind': act_kind, 'description': description}
        spec_raw.update(act_payload)
        action_spec = normalize_action_spec(spec_raw)
        return {'trigger': trigger, 'action_spec': action_spec}
    except Exception as exc:
        logger.debug("[InstrFollow] ready parse failed: %s", exc)
        return None


def _ready_state(battle, entity, description: str,
                 enemies: Optional[List[str]]) -> str:
    lines = [
        f"Entity: {getattr(entity, 'name', '?')} is readying (holding) an "
        "action in combat.",
        f"The player's own words: {description!r}",
    ]
    try:
        foes = list(enemies or [])
        lines.append("visible foes: " + (", ".join(foes) or "unknown"))
    except Exception:
        pass
    lines.append(
        "Answer the trigger question and the action question from the "
        "options given; the options are the only legal choices."
    )
    return _fit_state(lines)


def _ready_decide(provider, state: str, instructions: str,
                  options: List[str]) -> Optional[int]:
    try:
        from natural20.concurrency import run_blocking
        res = run_blocking(provider.decide_action, state, options)
    except Exception as exc:
        logger.debug("[InstrFollow] ready decide failed: %s", exc)
        return None
    if not res:
        return None
    try:
        idx = int(res.get('index'))
    except (TypeError, ValueError):
        return None
    return idx if 0 <= idx < len(options) else None


def _known_weapons(entity) -> List[str]:
    out: List[str] = []
    try:
        for w in entity.equipped_weapons(entity.session) or []:
            slug = w.get('name') if isinstance(w, dict) else getattr(w, 'name', None)
            if slug:
                out.append(str(slug))
    except Exception:
        pass
    return out


def _known_spells(entity) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        for name in entity.prepared_spells() or []:
            out.append({'name': str(name)})
    except Exception:
        pass
    return out


def _known_items(entity) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        for it in entity.usable_items() or []:
            slug = it.get('slug') or it.get('name')
            if slug:
                out.append({'slug': str(slug), 'label': str(it.get('label') or slug)})
    except Exception:
        pass
    return out


def _ready_action_options(weapons, spells, items) -> List[str]:
    options: List[str] = []
    for w in weapons:
        options.append(f"attack with {w}")
    for s in spells:
        name = s.get('name') if isinstance(s, dict) else str(s)
        options.append(f"cast {name}")
    for it in items:
        label = (it.get('label') or it.get('slug')) if isinstance(it, dict) else str(it)
        options.append(f"use {label}")
    options.append("move (walk toward the trigger)")
    if len(options) > MAX_READY_ACTIONS:
        options = options[:MAX_READY_ACTIONS]
    return options


def _ready_action_payload(option: str) -> Tuple[str, Dict[str, Any]]:
    text = (option or '').strip()
    if text.startswith('attack with '):
        return 'attack', {'weapon': text[len('attack with '):]}
    if text.startswith('cast '):
        return 'spell', {'spell': text[len('cast '):]}
    if text.startswith('use '):
        return 'use_item', {'item': text[len('use '):]}
    return 'move', {}


__all__ = [
    'DEFAULT_INSTRUCTION_BUDGET',
    'InstructionEndTurn',
    'InstructionPlanner',
    'InstructionReady',
    'InstructionStop',
    'follow_instruction_step',
    'is_instruction_sentinel',
    'parse_player_instruction',
    'provider_can_follow_instructions',
]
