"""Loss-of-control foundation: pluggable wrappers around an entity's
controller that intercept action selection while a condition is active.

A ``ControlOverride`` wraps an entity's *base* controller (Generic, Web,
LLM, etc.) and applies one of three policies — in this order:

1. ``filter_actions`` shrinks the menu of available actions before the
   controller chooses (e.g. Charmed strips attacks at the charmer).
2. ``force_action`` may return an :class:`~natural20.action.Action` to
   override the controller's choice entirely (e.g. Confusion's d10
   table, Domination handing the wheel to the charmer).
3. Anything else is delegated to the wrapped base controller.

Multiple overrides can stack — see :class:`ControlOverrideStack`.

This module is intentionally small and side-effect free: registering
overrides on a battle is the responsibility of :mod:`natural20.battle`.
The condition-specific subclasses live under
``natural20/controllers/conditions/``.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from natural20.controller import Controller


class ControlOverride(Controller):
    """Base wrapper. Subclasses override the policy hooks they need.

    Subclasses should *not* override :meth:`select_action` /
    :meth:`move_for` directly unless they need to bypass the standard
    filter→force→delegate pipeline.
    """

    #: Higher priority overrides run first when multiple are stacked.
    #: ``force_action`` from a higher-priority override wins.
    PRIORITY: int = 0

    #: Short identifier (e.g. ``'frightened'``) used for save/load and
    #: to dedupe against the same source.
    CONDITION_ID: str = 'control_override'

    def __init__(self, base_controller: Controller, source=None,
                 condition_id: Optional[str] = None,
                 expires_round: Optional[int] = None):
        # Avoid calling ``Controller.__init__`` to keep state pristine —
        # the wrapper holds no battle_data of its own; it forwards.
        self.base = base_controller
        self.source = source
        self.condition_id = condition_id or self.CONDITION_ID
        self.expires_round = expires_round
        self.session = getattr(base_controller, 'session', None)
        self.user = getattr(base_controller, 'user', None)

    # ---- policy hooks (subclass overrides) -----------------------------

    def filter_actions(self, entity, battle, actions: List) -> List:
        """Return the subset of ``actions`` the entity may take.

        Default: pass-through.
        """
        return list(actions)

    def force_action(self, entity, battle, actions: List):
        """Return an :class:`Action` that must be taken now, or ``None``
        to defer to the wrapped controller.
        """
        return None

    def force_move(self, entity, battle):
        """Return a forced move :class:`Action`, or ``None`` to defer to
        the wrapped controller's normal movement selection.
        """
        return None

    def block_reactions(self, entity, event) -> bool:
        """Return ``True`` to suppress reactions (opportunity attacks,
        Shield, Counterspell, etc.) while this override is active.
        """
        return False

    # ---- standard pipeline --------------------------------------------

    def select_action(self, battle, entity, available_actions=None):
        actions = list(available_actions or [])
        actions = self.filter_actions(entity, battle, actions)
        forced = self.force_action(entity, battle, actions)
        if forced is not None:
            return forced
        return self.base.select_action(battle, entity, actions)

    def move_for(self, entity, battle):
        forced = self.force_move(entity, battle)
        if forced is not None:
            return forced
        return self.base.move_for(entity, battle)

    # ---- listener delegation (with reaction-block gate) ---------------

    def opportunity_attack_listener(self, battle, session, entity, _map, event):
        if self.block_reactions(entity, event):
            return None
        if hasattr(self.base, 'opportunity_attack_listener'):
            return self.base.opportunity_attack_listener(
                battle, session, entity, _map, event,
            )
        return None

    def legendary_action_listener(self, battle, session, entity, _map, event):
        if self.block_reactions(entity, event):
            return None
        if hasattr(self.base, 'legendary_action_listener'):
            return self.base.legendary_action_listener(
                battle, session, entity, _map, event,
            )
        return None

    def select_reaction(self, entity, battle, _map, valid_actions, event):
        if self.block_reactions(entity, event):
            return None
        if hasattr(self.base, 'select_reaction'):
            return self.base.select_reaction(entity, battle, _map, valid_actions, event)
        return None

    def spell_reaction(self, entity, battle, action):
        if self.block_reactions(entity, None):
            return False
        if hasattr(self.base, 'spell_reaction'):
            return self.base.spell_reaction(entity, battle, action)
        return False

    def begin_turn(self, entity):
        if hasattr(self.base, 'begin_turn'):
            self.base.begin_turn(entity)

    def roll_for(self, entity, stat, advantage=False, disadvantage=False):
        if hasattr(self.base, 'roll_for'):
            return self.base.roll_for(entity, stat, advantage, disadvantage)
        return None

    def register_handlers_on(self, entity):
        # Reuse the wrapped controller's handler registration so reactions
        # keep flowing through the existing event plumbing. Reaction-block
        # is enforced inside the listener wrappers above.
        if hasattr(self.base, 'register_handlers_on'):
            self.base.register_handlers_on(entity)

    # ---- attribute fall-through ---------------------------------------

    def __getattr__(self, name):
        # Anything we don't explicitly model falls through to the base
        # controller so that tool-specific hooks (LLM prompt building,
        # WebController user lists, etc.) keep working transparently.
        # ``__getattr__`` is only called when the normal lookup fails,
        # so wrapper-defined attributes remain authoritative.
        base = object.__getattribute__(self, 'base')
        return getattr(base, name)

    # ---- introspection / serialization --------------------------------

    def describe(self) -> str:
        src = getattr(self.source, 'name', self.source)
        return f"{self.condition_id} from {src}"

    def to_dict(self):
        return {
            'class_id': f"{self.__class__.__module__}:{self.__class__.__name__}",
            'condition_id': self.condition_id,
            'source_uid': getattr(self.source, 'entity_uid', None),
            'expires_round': self.expires_round,
            'priority': self.PRIORITY,
        }


class ControlOverrideStack(Controller):
    """Composes multiple :class:`ControlOverride` instances into a single
    controller-shaped object.

    Action filtering composes left-to-right (each override narrows the
    set further). ``force_action`` / ``force_move`` short-circuit on the
    first non-``None`` result, scanned in descending priority order.
    """

    def __init__(self, base_controller: Controller, overrides: Iterable[ControlOverride]):
        self.base = base_controller
        self.overrides: List[ControlOverride] = self._sort(list(overrides))
        self.session = getattr(base_controller, 'session', None)
        self.user = getattr(base_controller, 'user', None)

    @staticmethod
    def _sort(overrides: List[ControlOverride]) -> List[ControlOverride]:
        return sorted(overrides, key=lambda o: -getattr(o, 'PRIORITY', 0))

    def select_action(self, battle, entity, available_actions=None):
        actions = list(available_actions or [])
        for ov in self.overrides:
            actions = ov.filter_actions(entity, battle, actions)
        for ov in self.overrides:
            forced = ov.force_action(entity, battle, actions)
            if forced is not None:
                return forced
        return self.base.select_action(battle, entity, actions)

    def move_for(self, entity, battle):
        for ov in self.overrides:
            forced = ov.force_move(entity, battle)
            if forced is not None:
                return forced
        return self.base.move_for(entity, battle)

    def opportunity_attack_listener(self, battle, session, entity, _map, event):
        for ov in self.overrides:
            if ov.block_reactions(entity, event):
                return None
        if hasattr(self.base, 'opportunity_attack_listener'):
            return self.base.opportunity_attack_listener(
                battle, session, entity, _map, event,
            )
        return None

    def legendary_action_listener(self, battle, session, entity, _map, event):
        for ov in self.overrides:
            if ov.block_reactions(entity, event):
                return None
        if hasattr(self.base, 'legendary_action_listener'):
            return self.base.legendary_action_listener(
                battle, session, entity, _map, event,
            )
        return None

    def select_reaction(self, entity, battle, _map, valid_actions, event):
        for ov in self.overrides:
            if ov.block_reactions(entity, event):
                return None
        if hasattr(self.base, 'select_reaction'):
            return self.base.select_reaction(entity, battle, _map, valid_actions, event)
        return None

    def spell_reaction(self, entity, battle, action):
        for ov in self.overrides:
            if ov.block_reactions(entity, None):
                return False
        if hasattr(self.base, 'spell_reaction'):
            return self.base.spell_reaction(entity, battle, action)
        return False

    def begin_turn(self, entity):
        if hasattr(self.base, 'begin_turn'):
            self.base.begin_turn(entity)

    def roll_for(self, entity, stat, advantage=False, disadvantage=False):
        if hasattr(self.base, 'roll_for'):
            return self.base.roll_for(entity, stat, advantage, disadvantage)
        return None

    def register_handlers_on(self, entity):
        if hasattr(self.base, 'register_handlers_on'):
            self.base.register_handlers_on(entity)

    def __getattr__(self, name):
        base = object.__getattribute__(self, 'base')
        return getattr(base, name)
