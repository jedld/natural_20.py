"""
Jev (TypeSafe "System One") recursive action-tree planner for NPC combat AI.

Design
------
Instead of asking the decision model to pick a single index out of a flat list
of fully-built actions, the planner walks the action space *recursively*,
mirroring how the action builder (``natural20.utils.action_builder``) expands
an action's ``build_map()`` tree:

    1. ACTION TYPE   attack | spell | move | help | dodge | hide | ...
                     (one JEV ``Choice`` over the types available right now)
    2. DECOMPOSITION recursively resolved with one JEV ``Choice`` per level:
        - attack  -> weapon -> target
        - spell   -> spell name (+ level) -> target / AoE anchor / ...
        - help    -> ally target
        - move    -> *special handling*, a strategic intent first:
                       move -> entity (close to melee range of chosen foe)
                       move -> defensive square (cover / away from foes)
                       move -> hide (reachable hiding spot)
                       move -> offensive square (improved attack position)
                     then the concrete destination square.
        - dodge / dash / hide / stand / look / second_wind / ...  -> leaf
    3. MATERIALIZATION the chosen path is materialized into a fully
       parameterized ``Action`` (via the ``build_map`` ``next`` callbacks /
       ``autobuild`` with a ``match``), so the battle loop executes it exactly
       like a player-built action.

Every level is a single ``JevProvider.decide_action(state, options)`` call
(compact option descriptions, <= 255 options). If *any* level fails (no
client, SDK error, out-of-range answer, no legal options) the planner returns
``None`` and the controller falls back to its heuristic ranking.

The module is deliberately provider-agnostic: it only requires an object with
a ``decide_action(state, options) -> dict|None`` method (``JevProvider``
satisfies this). All heavy lifting is wrapped in defensive try/excepts so a
decision failure can never crash the battle loop.
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Jev's Choice question is capped at 255 criteria; stay safely below.
MAX_JEV_OPTIONS = 24
# Hard cap on the number of decide_action round-trips per turn.
DEFAULT_MAX_DECISIONS = 8


# --------------------------------------------------------------------------- #
# Small helpers                                                               #
# --------------------------------------------------------------------------- #

def _name(x) -> str:
    try:
        n = getattr(x, 'name', None)
        if callable(n):
            n = n()
        if n:
            return str(n)
    except Exception:
        pass
    return str(x)


def _hp_text(entity) -> str:
    try:
        return f"{entity.hp()}/{entity.max_hp()}"
    except Exception:
        return "?"


def _dist_ft(battle, map_, a, b) -> Optional[int]:
    try:
        if map_ is None:
            return None
        d = map_.distance(a, b) * (getattr(map_, 'feet_per_grid', 5) or 5)
        return int(round(d))
    except Exception:
        return None


def _in_battle(map_, x, y) -> bool:
    try:
        size = map_.size
        return 0 <= x < size[0] and 0 <= y < size[1]
    except Exception:
        return False


def _cover_rank(cover) -> int:
    return {'none': 0, 'half': 1, 'three_quarter': 2, 'total': 3}.get(cover, 0)


def _oa_risk(battle, entity, path) -> bool:
    """True if moving along ``path`` would provoke an opportunity attack."""
    try:
        if entity.disengage(battle):
            return False
        m = battle.map_for(entity)
        if not m or not path:
            return False
        start = m.entity_or_object_pos(entity)
        if start:
            path = [start] + list(path[1:]) if path[0] != start else list(path)
        enemies = [e for e in battle.opponents_of(entity) if e.conscious()]
        feet = getattr(m, 'feet_per_grid', 5) or 5
        for foe in enemies:
            reach = (foe.melee_distance() or 5) / feet
            in_melee = None
            for pos in path:
                d = m.distance(entity, foe, entity_1_pos=pos)
                now = d <= reach
                if in_melee is True and not now:
                    return True
                in_melee = now if in_melee is None else in_melee
        return False
    except Exception:
        return False


def _oa_risk_to_square(battle, entity, dest) -> bool:
    try:
        m = battle.map_for(entity)
        if not m:
            return False
        pc = getattr(entity, 'npc', None)
        pc = pc() if callable(pc) else bool(pc)
        from natural20.ai.path_compute import PathCompute
        plan = PathCompute(battle, m, entity, ignore_opposing=not pc)
        path = plan.compute_path(*m.position_of(entity), dest[0], dest[1],
                                 available_movement_cost=entity.available_movement(battle))
        if not path:
            return False
        return _oa_risk(battle, entity, path)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Action-class eligibility                                                    #
# --------------------------------------------------------------------------- #

def _class_can(action_class, entity, battle) -> bool:
    """Call ``action_class.can`` tolerating both signatures.

    The base class declares ``Action.can(entity, battle, options=None)`` but a
    number of subclasses override it with the 2-arg form ``can(entity, battle)``
    (e.g. MoveAction, DodgeAction, HelpAction). Passing ``options`` positionally
    or by keyword to those overrides raises TypeError and would silently drop
    the whole action class from the planner's menu.
    """
    import inspect
    try:
        params = inspect.signature(action_class.can).parameters
    except (TypeError, ValueError):
        params = {}
    if len(params) >= 3 or any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                                for p in params.values()):
        return bool(action_class.can(entity, battle, None))
    return bool(action_class.can(entity, battle))


# --------------------------------------------------------------------------- #
# Planner                                                                     #
# --------------------------------------------------------------------------- #

class JevActionPlanner:
    """Recursively turn JEV decisions into a fully-parameterized Action.

    Parameters
    ----------
    provider:
        Object with ``decide_action(state, options) -> {'index': int, ...}|None``.
        ``webapp.llm_handler.JevProvider`` satisfies this contract.
    max_decisions:
        Safety cap on JEV round-trips per ``select_action`` call.
    """

    def __init__(self, provider, max_decisions: int = DEFAULT_MAX_DECISIONS):
        self.provider = provider
        self.max_decisions = max_decisions
        self._decisions = 0
        # Populated on the first descent of a turn, reused by deeper levels.
        self._state = None
        self._battle = None
        self._entity = None
        self._map = None

    # -- decision budget ---------------------------------------------------- #
    def _decide(self, state: str, options: List[str]) -> Optional[int]:
        """One JEV Choice; returns 0-based index or None."""
        if self.provider is None or not options:
            return None
        if self._decisions >= self.max_decisions:
            logger.debug("[JevPlan] decision budget exhausted; stopping descent")
            return None
        opts = options[:MAX_JEV_OPTIONS]
        try:
            from natural20.concurrency import run_blocking
            res = run_blocking(self.provider.decide_action, state, opts)
        except Exception as e:
            logger.debug("[JevPlan] decide_action failed: %s", e)
            return None
        self._decisions += 1
        if not res:
            return None
        idx = res.get('index')
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            return None
        if not (0 <= idx < len(opts)):
            return None
        return idx

    # -- state rendering ---------------------------------------------------- #
    def _render_state(self, battle, entity) -> str:
        """Compact, unstructured state text handed to every JEV question."""
        m = battle.map_for(entity)
        feet = getattr(m, 'feet_per_grid', 5) or 5 if m else 5
        lines = []
        try:
            pos = m.position_of(entity) if m else None
            lines.append(
                f"Entity: {entity.name}; HP {_hp_text(entity)}; "
                f"pos {pos}; movement {entity.available_movement(battle)} ft; speed {entity.speed()} ft"
            )
            try:
                st = battle.entity_state_for(entity)
                if st and st.get('statuses'):
                    lines.append("statuses: " + ", ".join(sorted(st['statuses'])))
            except Exception:
                pass
            try:
                if entity.concentration():
                    lines.append("concentrating")
            except Exception:
                pass

            enemies = [e for e in battle.opponents_of(entity) if battle.can_see(entity, e) and not e.dead()]
            elines = []
            for e in enemies:
                d = _dist_ft(battle, m, entity, e)
                elines.append(f"{e.name} hp {_hp_text(e)} {d} ft" + (f" melee" if (d or 99) <= 5 else ""))
            lines.append("visible enemies: " + (", ".join(elines) or "none"))

            allies = []
            try:
                allies = [a for a in battle.allies_of(entity)
                          if a is not entity and battle.can_see(entity, a) and not a.dead()]
            except Exception:
                pass
            alines = [f"{a.name} hp {_hp_text(a)}" for a in allies]
            lines.append("allies: " + (", ".join(alines) or "none"))

            # spell slots, if any
            try:
                slots = []
                for lvl in range(1, 10):
                    mx = entity.max_spell_slots(lvl) if hasattr(entity, 'max_spell_slots') else 0
                    if mx:
                        cur = entity.spell_slots_count(lvl)
                        slots.append(f"L{lvl} {cur}/{mx}")
                if slots:
                    lines.append("spell slots: " + ", ".join(slots))
            except Exception:
                pass
            lines.append(
                "Task: choose the single best option index for the NEXT decision level. "
                "Prefer actions that win the fight and keep the entity alive."
            )
        except Exception as e:
            logger.debug("[JevPlan] state render failed: %s", e)
            lines.append("State unavailable.")
        return "\n".join(lines)

    # -- top level ---------------------------------------------------------- #
    def select(self, battle, entity, available_actions: Optional[List] = None) -> Optional[Any]:
        """Recursively build the action tree and return a parameterized Action."""
        try:
            self._battle = battle
            self._entity = entity
            self._map = battle.map_for(entity)
            self._session = getattr(battle, 'session', None)
            self._decisions = 0
            self._state = self._render_state(battle, entity)

            groups = self._collect_groups(available_actions)
            if not groups:
                return None

            type_options = []
            for t, actions in groups.items():
                type_options.append(self._type_desc(t, actions))

            tidx = self._decide(self._state, type_options)
            if tidx is None:
                return None
            chosen_type = list(groups.keys())[tidx]
            logger.debug("[JevPlan] %s chose action type '%s'",
                         getattr(entity, 'name', '?'), chosen_type)

            if chosen_type == 'move':
                return self._plan_move()

            action = self._plan_typed(chosen_type, groups[chosen_type])
            if action is None:
                return None
            return self._enrich(battle, entity, action)
        except Exception as e:
            logger.debug("[JevPlan] planner failed: %s", e)
            return None

    # -- action-type grouping ------------------------------------------------ #
    def _collect_groups(self, available_actions: Optional[List]) -> Dict[str, List]:
        """Group candidate actions by top-level type.

        When ``available_actions`` is supplied (the battle loop's pre-built
        list) we group it directly; otherwise we autobuild each valid action
        class so the tree is fully materializable.
        """
        from natural20.generic_controller import GenericController
        from natural20.utils.action_builder import autobuild

        groups: Dict[str, List] = {}

        def add(action):
            if action is None or getattr(action, 'disabled', False):
                return
            t = self._type_key(action)
            groups.setdefault(t, []).append(action)

        if available_actions:
            for a in available_actions:
                add(a)
            return groups

        session = getattr(self, '_session', None) or self._battle.session
        self._session = session
        for klass in self._action_classes(session):
            try:
                if not _class_can(klass, self._entity, self._battle):
                    continue
            except Exception:
                continue
            try:
                built = autobuild(session, klass, self._entity, self._battle,
                                  map=self._map, auto_target=False)
            except Exception:
                continue
            for a in built:
                add(a)
        return groups

    def _action_classes(self, session):
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.spell_action import SpellAction
        from natural20.actions.move_action import MoveAction
        from natural20.actions.help_action import HelpAction
        from natural20.actions.dodge_action import DodgeAction
        from natural20.actions.hide_action import HideAction
        from natural20.actions.dash import DashAction
        from natural20.actions.disengage_action import DisengageAction
        from natural20.actions.stand_action import StandAction
        from natural20.actions.look_action import LookAction
        from natural20.actions.second_wind_action import SecondWindAction
        from natural20.actions.use_item_action import UseItemAction
        from natural20.actions.interact_action import InteractAction
        from natural20.actions.shove_action import ShoveAction
        from natural20.actions.grapple_action import GrappleAction
        return [
            AttackAction, SpellAction, MoveAction, HelpAction, DodgeAction,
            HideAction, DashAction, DisengageAction, StandAction, LookAction,
            SecondWindAction, UseItemAction, InteractAction, ShoveAction,
            GrappleAction,
        ]

    @staticmethod
    def _type_key(action) -> str:
        """Group by action *class*, not the ``action_type`` string (some
        builders set misleading action_type values, e.g. DodgeAction)."""
        try:
            from natural20.actions.attack_action import AttackAction
            from natural20.actions.spell_action import SpellAction
            from natural20.actions.move_action import MoveAction
            from natural20.actions.help_action import HelpAction
            from natural20.actions.dodge_action import DodgeAction
            from natural20.actions.hide_action import HideAction
            from natural20.actions.dash import DashAction
            from natural20.actions.disengage_action import DisengageAction
            from natural20.actions.stand_action import StandAction
            from natural20.actions.look_action import LookAction
            from natural20.actions.second_wind_action import SecondWindAction
            from natural20.actions.use_item_action import UseItemAction
            from natural20.actions.interact_action import InteractAction
            from natural20.actions.shove_action import ShoveAction
            from natural20.actions.grapple_action import GrappleAction
            if isinstance(action, AttackAction):
                return 'attack'
            if isinstance(action, SpellAction):
                return 'spell'
            if isinstance(action, (MoveAction, DashAction, DisengageAction)):
                return 'move'
            if isinstance(action, HelpAction):
                return 'help'
            if isinstance(action, DodgeAction):
                return 'dodge'
            if isinstance(action, HideAction):
                return 'hide'
            if isinstance(action, StandAction):
                return 'stand'
            if isinstance(action, LookAction):
                return 'look'
            if isinstance(action, SecondWindAction):
                return 'second_wind'
            if isinstance(action, UseItemAction):
                return 'use_item'
            if isinstance(action, InteractAction):
                return 'interact'
            if isinstance(action, ShoveAction):
                return 'shove'
            if isinstance(action, GrappleAction):
                return 'grapple'
            at = getattr(action, 'action_type', None)
            if at:
                return str(at)
        except Exception:
            pass
        return 'other'

    @staticmethod
    def _type_desc(t: str, actions: List) -> str:
        if t == 'attack':
            names = sorted({_weapon_name(a) for a in actions if _weapon_name(a)})
            return f"attack (weapons: {', '.join(names) or '?'})"
        if t == 'spell':
            names = sorted({_spell_name(a) for a in actions if _spell_name(a)})
            shown = names[:6]
            more = f" +{len(names) - 6} more" if len(names) > 6 else ""
            return f"cast a spell ({', '.join(shown) or '?'}{more})"
        if t == 'move':
            return "move (reposition: engage, defensive, hide, or offensive square)"
        if t == 'help':
            return "help an ally (grants ally advantage / helps its checks)"
        if t == 'dodge':
            return "dodge (disadvantage on attacks against you until next turn)"
        if t == 'hide':
            return "hide (make a DEX (Stealth) check to become unseen)"
        if t == 'use_item':
            return "use an item"
        if t == 'interact':
            return "interact with a nearby object"
        return t.replace('_', ' ')

    # -- move: special strategic handling ----------------------------------- #
    def _plan_move(self) -> Optional[Any]:
        """move -> intent -> concrete destination square.

        Intents (only those currently legal are offered):
          0. entity       close to an enemy so we are in its melee range
          1. defensive    a safe square (cover, no OA, away from enemies)
          2. hide         a reachable hiding spot
          3. offensive    a square that improves our attack position
        """
        from natural20.actions.move_action import MoveAction
        from natural20.ai.path_compute import PathCompute

        m = self._map
        ent = self._entity
        battle = self._battle
        if m is None:
            return None

        pos = m.position_of(ent)
        move_ft = ent.available_movement(battle)
        if move_ft <= 0:
            return None

        pc = getattr(ent, 'npc', None)
        pc = pc() if callable(pc) else bool(pc)
        pc_calc = PathCompute(battle, m, ent, ignore_opposing=not pc)

        def path_to(dest):
            try:
                return pc_calc.compute_path(pos[0], pos[1], dest[0], dest[1],
                                            available_movement_cost=move_ft)
            except Exception:
                return None

        def dest_ok(dest, path):
            if not path or len(path) < 2:
                return False
            end = tuple(path[-1])
            if not m.placeable(ent, *end, battle):
                return False
            try:
                if m.entity_at(*end) is not None and m.entity_at(*end) is not ent:
                    return False
            except Exception:
                pass
            return end

        # ---- intent 0: move -> entity (melee range) ---- #
        melee_opts = []
        try:
            enemies = [e for e in battle.opponents_of(ent)
                       if battle.can_see(ent, e) and not e.dead() and e.conscious()]
            for e in enemies:
                epos = m.position_of(e)
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        if dx == 0 and dy == 0:
                            continue
                        cand = (epos[0] + dx, epos[1] + dy)
                        if not _in_battle(m, cand[0], cand[1]):
                            continue
                        if m.entity_at(cand[0], cand[1]) is not None:
                            continue
                        p = path_to(cand)
                        if not dest_ok(cand, p):
                            continue
                        melee_opts.append((cand, p))
        except Exception:
            pass
        # keep nearest per enemy
        seen = set()
        melee_uniq = []
        for cand, p in melee_opts:
            if cand in seen:
                continue
            seen.add(cand)
            melee_uniq.append((cand, p))

        # ---- intent 1/3: defensive & offensive squares ---- #
        def candidate_squares():
            sqs = []
            maxr = max(1, int(move_ft // (getattr(m, 'feet_per_grid', 5) or 5)))
            for dx in range(-maxr, maxr + 1):
                for dy in range(-maxr, maxr + 1):
                    if dx == 0 and dy == 0:
                        continue
                    cand = (pos[0] + dx, pos[1] + dy)
                    if not _in_battle(m, cand[0], cand[1]):
                        continue
                    p = path_to(cand)
                    if not dest_ok(cand, p):
                        continue
                    sqs.append((cand, p))
            return sqs

        def enemy_dists(cand):
            ds = []
            try:
                for e in battle.opponents_of(ent):
                    if battle.can_see(ent, e) and not e.dead():
                        ds.append(m.distance(ent, e, entity_1_pos=cand) *
                                  (getattr(m, 'feet_per_grid', 5) or 5))
            except Exception:
                pass
            return ds

        defensive = []
        offensive = []
        try:
            enemies = [e for e in battle.opponents_of(ent)
                       if battle.can_see(ent, e) and not e.dead() and e.conscious()]
            for cand, p in candidate_squares():
                cover = 'none'
                try:
                    cover = m.cover_at(cand[0], cand[1], origin=pos) or 'none'
                except Exception:
                    pass
                oa = _oa_risk(battle, ent, p)
                ds = enemy_dists(cand)
                min_d = min(ds) if ds else None
                line = f"{cand}"
                if cover != 'none':
                    defensive.append((cand, p, cover, oa, min_d, line))
                # offensive: in melee reach of at least one foe, without OA,
                # and with cover if available
                if any((d or 99) <= 5 for d in ds) and not oa:
                    offensive.append((cand, p, cover, oa, min_d, line))
        except Exception:
            pass

        # rank defensive: more cover, no OA, farther from enemies
        defensive.sort(key=lambda x: (
            -_cover_rank(x[2]), x[3], x[4] if x[4] is not None else 0))
        # rank offensive: prefer cover, then closer to most enemies
        offensive.sort(key=lambda x: (
            -_cover_rank(x[2]), x[3] and 1 or 0, -(x[4] if x[4] is not None else 0)))

        # ---- intent 2: hide ---- #
        hide_opts = []
        try:
            spots = m.hiding_spots_for(ent, battle)
            for s in spots:
                cand = (int(s[0]), int(s[1]))
                if not _in_battle(m, cand[0], cand[1]):
                    continue
                p = path_to(cand)
                if dest_ok(cand, p):
                    hide_opts.append((cand, p))
        except Exception:
            pass
        hide_opts.sort(key=lambda x: len(x[1]))

        # ---- offer the intents that have options ---- #
        intents = []  # (label, kind, options)
        if melee_uniq:
            enemies = [e for e in battle.opponents_of(ent)
                       if battle.can_see(ent, e) and not e.dead()]
            labels = []
            for cand, p in melee_uniq[:MAX_JEV_OPTIONS]:
                near = [
                    _name(e)
                    for e in enemies
                    if m.position_of(e) is not None
                    and abs(m.position_of(e)[0] - cand[0]) <= 1
                    and abs(m.position_of(e)[1] - cand[1]) <= 1
                ]
                labels.append(f"engage {', '.join(near) or 'nearest foe'}: {cand}")
            intents.append(("move to melee range of an enemy (close the gap and be able to attack it next)",
                            'melee', melee_uniq[:MAX_JEV_OPTIONS], labels[:MAX_JEV_OPTIONS]))
        if defensive:
            labels = [
                f"{cand} [{cov} cover, {'OA' if oa else 'safe'}, {int(d) if d is not None else 0} ft from nearest foe)"
                for cand, p, cov, oa, d, _ in defensive[:MAX_JEV_OPTIONS]
            ]
            intents.append(("move to a defensive square (cover and/or away from enemies)",
                            'defensive', defensive[:MAX_JEV_OPTIONS], labels[:MAX_JEV_OPTIONS]))
        if hide_opts:
            labels = [f"hide at {cand} ({len(p) - 1} steps)" for cand, p in hide_opts[:MAX_JEV_OPTIONS]]
            intents.append(("move to a hiding spot and become hidden", 'hide',
                            hide_opts[:MAX_JEV_OPTIONS], labels[:MAX_JEV_OPTIONS]))
        if offensive:
            labels = [
                f"{cand} [{'OA-free' if not oa else 'OA-risk'}, in reach of {int(d)} ft foe{', ' + cov if cov != 'none' else ''})"
                for cand, p, cov, oa, d, _ in offensive[:MAX_JEV_OPTIONS]
            ]
            intents.append(("move to an offensive square (improve your attack position)",
                            'offensive', offensive[:MAX_JEV_OPTIONS], labels[:MAX_JEV_OPTIONS]))

        if not intents:
            return None

        idx = self._decide(self._state, [i[0] for i in intents])
        if idx is None:
            return None
        _, kind, options, labels = intents[idx]
        logger.debug("[JevPlan] move intent: %s (%d options)", kind, len(options))

        oidx = self._decide(
            self._state + "\nChosen movement intent: " + intents[idx][0],
            labels)
        if oidx is None:
            return None
        cand, path = options[oidx][0], options[oidx][1]

        action = MoveAction(self._session, ent, 'move')
        action.move_path = list(path)
        return action

    # -- typed planning (attack / spell / help / ...) ------------------------- #
    def _plan_typed(self, type_key: str, built_actions: List) -> Optional[Any]:
        """Materialize the chosen type into one concrete, parameterized action.

        Strategy: rebuild the type's ``build_map`` tree and descend it level by
        level with JEV decisions (weapon -> target, spell -> target/AoE, ...).
        If the descent fails, fall back to choosing among the pre-built leaf
        actions of the same type with one final JEV choice.
        """
        from natural20.utils.action_builder import autobuild

        action_cls = self._class_for_type(type_key)
        if action_cls is not None:
            try:
                root = action_cls.build(self._session, self._entity)
                if isinstance(root, dict) and root.get('param'):
                    leaf = self._descend(root)
                    if leaf is not None:
                        return leaf
            except Exception as e:
                logger.debug("[JevPlan] descent for %s failed: %s", type_key, e)

        # Fallback: pick among the pre-built leaf actions of this type.
        if built_actions:
            if len(built_actions) == 1:
                return built_actions[0]
            descs = [_leaf_desc(a) for a in built_actions[:MAX_JEV_OPTIONS]]
            idx = self._decide(self._state, descs)
            if idx is not None:
                return built_actions[idx]
        return None

    def _class_for_type(self, type_key: str):
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.spell_action import SpellAction
        from natural20.actions.move_action import MoveAction
        from natural20.actions.help_action import HelpAction
        from natural20.actions.dodge_action import DodgeAction
        from natural20.actions.hide_action import HideAction
        from natural20.actions.dash import DashAction
        from natural20.actions.disengage_action import DisengageAction
        from natural20.actions.stand_action import StandAction
        from natural20.actions.look_action import LookAction
        from natural20.actions.second_wind_action import SecondWindAction
        from natural20.actions.use_item_action import UseItemAction
        from natural20.actions.interact_action import InteractAction
        from natural20.actions.shove_action import ShoveAction
        from natural20.actions.grapple_action import GrappleAction
        return {
            'attack': AttackAction,
            'spell': SpellAction,
            'move': MoveAction,
            'help': HelpAction,
            'dodge': DodgeAction,
            'hide': HideAction,
            'dash': DashAction,
            'disengage': DisengageAction,
            'stand': StandAction,
            'look': LookAction,
            'second_wind': SecondWindAction,
            'use_item': UseItemAction,
            'interact': InteractAction,
            'shove': ShoveAction,
            'grapple': GrappleAction,
        }.get(type_key)

    # -- recursive descent over build_map dicts ------------------------------ #
    def _descend(self, node) -> Optional[Any]:
        """Recursively resolve a ``build_map`` node with one JEV choice per level."""
        from natural20.action import Action
        from natural20.utils.action_builder import build_params

        if isinstance(node, Action):
            return node
        if not isinstance(node, dict):
            return None
        if node is None:
            return None

        params = node.get('param') or []
        next_fn = node.get('next')
        if not params:
            # leaf dict without params: call next() with no args if possible
            try:
                return next_fn() if callable(next_fn) else node.get('action')
            except Exception:
                return node.get('action')

        # Build all legal options for every param slot in this level.
        try:
            options = build_params(self._session, self._entity, self._battle, node,
                                   map=self._map, auto_target=False)
        except Exception as e:
            logger.debug("[JevPlan] build_params failed: %s", e)
            return None
        if options is None:
            return None
        for opt in options:
            if not opt:
                return None

        # Describe each param's options and ask JEV to pick one per slot.
        chosen = []
        level_desc = []
        for param, opt_list in zip(params, options):
            descs = [_param_opt_desc(param, o) for o in opt_list[:MAX_JEV_OPTIONS]]
            idx = self._decide(self._state + "\nDecision level: " + _param_desc(param), descs)
            if idx is None:
                return None
            chosen.append(opt_list[idx])
            level_desc.append(f"{_param_desc(param)} -> {descs[idx]}")

        try:
            child = next_fn(*chosen)
        except Exception as e:
            logger.debug("[JevPlan] next() failed: %s", e)
            return None

        if isinstance(child, dict):
            return self._descend(child)
        return child

    # -- final enrichment ------------------------------------------------------ #
    def _enrich(self, battle, entity, action) -> Any:
        """Last-ditch defaults if the descent left a required param unset."""
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.spell_action import SpellAction
        try:
            if isinstance(action, AttackAction) and getattr(action, 'target', None) is None:
                targets = battle.valid_targets_for(entity, action, target_types=['enemies'])
                if targets:
                    action.target = sorted(targets, key=lambda t: (t.hp() or 0))[0]
            if isinstance(action, SpellAction):
                sa = getattr(action, 'spell_action', None)
                if sa is not None and getattr(sa, 'target', None) is None and \
                        getattr(action, 'target', None) is None:
                    targets = battle.valid_targets_for(entity, action, target_types=['enemies'])
                    if targets:
                        action.target = sorted(targets, key=lambda t: (t.hp() or 0))[0]
        except Exception:
            pass
        return action


# --------------------------------------------------------------------------- #
# Option description helpers (keep these SHORT: they become JEV criteria)     #
# --------------------------------------------------------------------------- #

def _weapon_name(action) -> Optional[str]:
    try:
        npc = getattr(action, 'npc_action', None)
        if isinstance(npc, dict):
            return npc.get('name')
        using = getattr(action, 'using', None)
        if using:
            return using
        opts = getattr(action, 'opts', None) or {}
        return opts.get('using')
    except Exception:
        return None


def _spell_name(action) -> Optional[str]:
    try:
        sp = getattr(action, 'spell', None) or (getattr(action, 'opts', None) or {}).get('spell')
        if isinstance(sp, dict):
            return sp.get('name') or sp.get('slug')
        if isinstance(sp, str):
            return sp
        sa = getattr(action, 'spell_action', None)
        if sa is not None:
            n = getattr(sa, 'short_name', None)
            if callable(n):
                return n()
            n = getattr(sa, 'name', None)
            if callable(n):
                return n()
            if isinstance(n, str):
                return n
        sp = getattr(action, 'spell', None)
        if isinstance(sp, dict):
            return sp.get('name')
    except Exception:
        return None


def _param_desc(param: Dict[str, Any]) -> str:
    ptype = param.get('type', '?')
    if ptype == 'select_target':
        kinds = param.get('target_types', ['enemies'])
        return f"target ({'/'.join(kinds)})"
    if ptype == 'select_spell':
        return "spell (name and level)"
    if ptype == 'select_weapon':
        return "weapon"
    if ptype == 'select_item':
        return "item"
    if ptype == 'select_object':
        return "object"
    if ptype == 'movement':
        return "destination square (one step)"
    if ptype in ('select_cone', 'select_cube', 'select_radius',
                 'select_square', 'select_line', 'select_empty_space'):
        return f"AoE anchor ({ptype.replace('select_', '')})"
    if ptype == 'select_choice':
        return "choice"
    return ptype


def _param_opt_desc(param: Dict[str, Any], opt: Any) -> str:
    """One-line description of a single parameter option (JEV criterion)."""
    ptype = param.get('type', '?')
    try:
        if ptype == 'select_target':
            nm = _name(opt)
            try:
                d = opt.hp()
                mx = opt.max_hp()
                hp = f" {d}/{mx}"
            except Exception:
                hp = ""
            return f"{nm}{hp}"
        if ptype == 'select_spell':
            name, lvl = opt if isinstance(opt, (list, tuple)) else (opt, 0)
            lvl_txt = 'cantrip' if not lvl else f'level {lvl}'
            return f"{name} ({lvl_txt})"
        if ptype == 'select_weapon':
            if isinstance(opt, dict):
                return opt.get('name', str(opt))
            return str(opt)
        if ptype == 'select_item':
            return str(opt)
        if ptype in ('movement', 'select_empty_space', 'select_cone',
                     'select_cube', 'select_radius', 'select_square', 'select_line'):
            if isinstance(opt, (list, tuple)) and len(opt) >= 2:
                return f"square ({opt[0]},{opt[1]})"
            return str(opt)
        if ptype == 'select_object':
            return _name(opt)
        if ptype == 'select_choice':
            return str(opt[0]) if isinstance(opt, (list, tuple)) and opt else str(opt)
        if ptype == 'interact':
            return str(opt[0]) if isinstance(opt, (list, tuple)) and opt else str(opt)
    except Exception:
        pass
    return str(opt)[:60]


def _leaf_desc(action) -> str:
    """One-line description of a fully-built leaf action (fallback choice)."""
    from natural20.actions.attack_action import AttackAction
    from natural20.actions.spell_action import SpellAction
    from natural20.actions.move_action import MoveAction
    try:
        if isinstance(action, AttackAction):
            w = _weapon_name(action) or 'weapon'
            t = getattr(action, 'target', None)
            return f"attack {_name(t) if t else 'target'} with {w}"
        if isinstance(action, SpellAction):
            s = _spell_name(action) or 'spell'
            t = getattr(action, 'target', None)
            tn = _name(t) if t else 'target'
            lvl = getattr(action, 'at_level', None) or getattr(action, 'level', None)
            lvl_txt = f" L{lvl}" if lvl else ""
            return f"cast {s}{lvl_txt} on {tn}"
        if isinstance(action, MoveAction):
            p = getattr(action, 'move_path', None)
            end = p[-1] if p else None
            return f"move to {tuple(end) if end else '?'}"
        t = getattr(action, 'target', None)
        if t is not None:
            return f"{action.action_type} {_name(t)}"
        return str(getattr(action, 'action_type', 'action')).replace('_', ' ')
    except Exception:
        return str(getattr(action, 'action_type', 'action'))


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #

def jev_select_action(provider, battle, entity,
                      available_actions: Optional[List] = None,
                      max_decisions: int = DEFAULT_MAX_DECISIONS) -> Optional[Any]:
    """Recursively plan an action with the JEV decision model.

    Returns a fully-parameterized ``Action`` or ``None`` (caller should then
    fall back to heuristic selection).
    """
    if provider is None or not getattr(provider, 'is_available', False):
        return None
    planner = JevActionPlanner(provider, max_decisions=max_decisions)
    return planner.select(battle, entity, available_actions)
