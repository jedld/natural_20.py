"""
Jev (TypeSafe "System One") action planner for NPC combat AI.

Design
------
The planner materializes the entity's whole action space into a flat list of
*fully-specified, currently-executable* leaf actions and asks the decision
model to pick one of them in a **single** ``decide_action`` call:

    - attack  -> one leaf per weapon x legal target
    - spell   -> one leaf per castable spell x legal target / AoE anchor
    - move    -> one leaf per strategic intent x destination square:
                   engage (close to melee range of a foe)
                   defensive (cover / away from foes)
                   hide (reachable hiding spot)
                   offensive (improved attack position)
    - help / shove / grapple / interact / use_item -> one leaf per legal target
    - dodge / dash / hide / stand / look / second_wind / ... -> single leaf
    - pass    -> always the final top-level leaf ("pass (end turn)"); the
                 model may end its turn instead of acting

Because every option is already a complete action, no follow-up round-trips
are needed: decision levels with a single legal option (one weapon, one
target, one square) are pruned implicitly, and actions that cannot be
completed right now (weapon attacks with no weapon, no legal target, no
usable item/object) are rejected before the question is built. When the whole
tree collapses to a single leaf the model is not consulted at all.

A ``pass (end turn)`` leaf (``EndTurnAction``) is appended as the final
top-level option on every call: ending the turn is always a legal choice.
Because of this, "single leaf" auto-selection only fires when nothing but
pass survived the pruning (i.e. there is nothing to do this turn).

``JevProvider.system_one`` answers a flat mapping of *independent* questions,
so a dependent decision tree cannot be sent as-is; flattening to leaves is
the one-call equivalent and keeps the model's answer unambiguously
consistent.

If no legal leaves exist, or the single call fails (no client, SDK error,
out-of-range answer), the planner returns ``None`` and the controller falls
back to its heuristic ranking.

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
MAX_JEV_OPTIONS = 24   # per-type cap on leaf options
MAX_JEV_LEAVES = 60    # total cap for the single flattened question
MAX_JEV_POV_LOG = 10   # max witnessed battle-log lines rendered into the state
# Kept for API compatibility; the flattened planner makes at most 1 call/turn.
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


def _ac_value(entity) -> Optional[int]:
    """The entity's current effective AC, or None when unknown/zero.

    ``armor_class()`` already folds in active ``ac_bonus`` effects (Haste +2,
    Shield +5, ...) and class features, so this is the number an attack roll
    is actually made against right now.
    """
    try:
        ac = entity.armor_class()
    except Exception:
        return None
    try:
        ac = int(ac)
    except (TypeError, ValueError):
        return None
    return ac if ac else None


def _effect_name(effect) -> Optional[str]:
    """Display name of a registered effect's spell (``Haste``), not its class."""
    if effect is None:
        return None
    props = getattr(effect, 'properties', None)
    if isinstance(props, dict):
        n = props.get('name') or props.get('label')
        if n:
            return n
    for attr in ('short_name', 'name'):
        n = getattr(effect, attr, None)
        if callable(n):
            try:
                n = n()
            except Exception:
                continue
        if isinstance(n, str) and n:
            return n
    return None


def _active_buffs(entity) -> List[str]:
    """Names of the timed effects/buffs currently active on the entity.

    Many buff spells (Shield, Mage Armor, Bless, Haste, ...) register their
    mechanics on ``entity.effects`` without adding a status, so the model
    only learns about them here. Descriptors are deduplicated by spell name
    (Haste registers both ``speed_override`` and ``ac_bonus``) and carry
    their remaining duration in seconds when bounded. Raw mechanism entries
    with no named spell are skipped.
    """
    try:
        now = entity.session.game_time
    except Exception:
        now = 0
    seen = set()
    out = []
    for descriptors in (getattr(entity, 'effects', None) or {}).values():
        for d in descriptors or []:
            try:
                exp = d.get('expiration')
                if exp is not None and exp <= now:
                    continue  # already expired
                name = _effect_name(d.get('effect'))
                if not name or name in seen:
                    continue
                seen.add(name)
                if exp is not None:
                    out.append(f"{name} {max(0, int(exp - now))}s")
                else:
                    out.append(name)
            except Exception:
                continue
    return out


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
    """Turn one JEV decision into a fully-parameterized Action.

    The action space is flattened to executable leaf actions (see the module
    docstring) and a single ``decide_action`` call picks among them; a tree
    with one legal leaf is auto-selected without any round-trip.

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
        # Populated once per turn; reused by the leaf question.
        self._state = None
        self._battle = None
        self._entity = None
        self._map = None
        self._session = None

    # -- decision budget ---------------------------------------------------- #
    def _decide(self, state: str, options: List[str]) -> Optional[int]:
        """One JEV Choice; returns 0-based index or None."""
        if self.provider is None or not options:
            return None
        if self._decisions >= self.max_decisions:
            logger.debug("[JevPlan] decision budget exhausted; stopping descent")
            return None
        opts = options[:MAX_JEV_LEAVES]
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
    def _display_names(self, battle, entity) -> dict:
        """id(entity) -> unambiguous display name.

        When an entity's name collides with the acting entity's or another
        listed entity's name (exact match or substring, e.g. ``Meringo`` vs
        ``Meringo (fighter2)``), its map position is appended
        (``Meringo@[7, 3]``) so state text and leaf descriptions stay
        unambiguous.
        """
        m = battle.map_for(entity) if battle else None
        others = []
        try:
            if battle is not None:
                others += [e for e in battle.opponents_of(entity) if not e.dead()]
                others += [a for a in battle.allies_of(entity)
                           if a is not entity and not a.dead()]
        except Exception:
            pass
        names = {id(entity): _name(entity)}
        me = _name(entity).lower()
        for o in others:
            name = _name(o)
            lo = name.lower()
            collides = lo == me or lo in me or me in lo
            if not collides:
                for p in others:
                    if p is o:
                        continue
                    po = _name(p).lower()
                    if lo == po or lo in po or po in lo:
                        collides = True
                        break
            if collides and m is not None:
                try:
                    pos = m.position_of(o)
                    name = f"{name}@[{pos[0]}, {pos[1]}]"
                except Exception:
                    pass
            names[id(o)] = name
        return names

    def _display_name(self, e) -> str:
        if e is None:
            return 'target'
        names = getattr(self, '_names', None)
        if names:
            return names.get(id(e), _name(e))
        return _name(e)

    def _render_state(self, battle, entity) -> str:
        """Compact, unstructured state text handed to every JEV question."""
        m = battle.map_for(entity)
        feet = getattr(m, 'feet_per_grid', 5) or 5 if m else 5
        lines = []
        try:
            pos = m.position_of(entity) if m else None
            ac = _ac_value(entity)
            ac_part = f"; AC {ac}" if ac is not None else ""
            lines.append(
                f"Entity: {entity.name}; HP {_hp_text(entity)}{ac_part}; "
                f"pos {pos}; movement {entity.available_movement(battle)} ft; speed {entity.speed()} ft"
            )
            try:
                # Merge the per-turn battle-state markers (dodge/disengage) with
                # the entity's own standing conditions (poisoned, prone,
                # grappled, hidden, unconscious, ...) - those live on
                # ``entity.statuses`` and are what every condition check reads.
                sts = set()
                st = battle.entity_state_for(entity)
                if st and st.get('statuses'):
                    sts.update(st['statuses'])
                own = getattr(entity, 'statuses', None)
                if own:
                    sts.update(own)
                sts.discard('dead')
                if sts:
                    lines.append("statuses: " + ", ".join(sorted(sts)))
            except Exception:
                pass
            try:
                if entity.concentration():
                    lines.append("concentrating")
            except Exception:
                pass
            try:
                lines.append(
                    "mods: str{:+d} dex{:+d} con{:+d} int{:+d} wis{:+d} cha{:+d}".format(
                        entity.str_mod(), entity.dex_mod(), entity.con_mod(),
                        entity.int_mod(), entity.wis_mod(), entity.cha_mod())
                )
            except Exception:
                pass

            enemies = [e for e in battle.opponents_of(entity) if battle.can_see(entity, e) and not e.dead()]
            elines = []
            for e in enemies:
                d = _dist_ft(battle, m, entity, e)
                extra = ""
                try:
                    if e.incapacitated():
                        extra = " (unconscious)"
                except Exception:
                    pass
                ac = _ac_value(e)
                ac_part = f" ac {ac}" if ac is not None else ""
                elines.append(f"{self._display_name(e)} hp {_hp_text(e)}{ac_part} {d} ft"
                              + (f" melee" if (d or 99) <= 5 else "") + extra)
            lines.append("visible enemies: " + (", ".join(elines) or "none"))

            allies = []
            try:
                allies = [a for a in battle.allies_of(entity)
                          if a is not entity and battle.can_see(entity, a) and not a.dead()]
            except Exception:
                pass
            alines = []
            for a in allies:
                ac = _ac_value(a)
                ac_part = f" ac {ac}" if ac is not None else ""
                alines.append(f"{self._display_name(a)} hp {_hp_text(a)}{ac_part}")
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

            # usable inventory (the same items the action space can use)
            try:
                items = []
                for it in entity.usable_items():
                    label = it.get('label') or it.get('name')
                    try:
                        qty = int(it.get('qty', 1) or 1)
                    except (TypeError, ValueError):
                        qty = 1
                    if not label:
                        continue
                    items.append(f"{label} x{qty}" if qty > 1 else str(label))
                    if len(items) >= 6:
                        break
                if items:
                    lines.append("items: " + ", ".join(items))
            except Exception:
                pass

            # active timed buffs (spells that register effects without a status)
            try:
                buffs = _active_buffs(entity)
                if buffs:
                    lines.append("effects: " + ", ".join(buffs))
            except Exception:
                pass

            # spent action/bonus action (normally 1/1 at the start of a turn)
            try:
                act = entity.total_actions(battle)
                bon = entity.total_bonus_actions(battle)
                if not act or not bon:
                    lines.append(f"resources: action={act}, bonus={bon}")
            except Exception:
                pass

            # POV: what the entity witnessed since its previous turn
            try:
                pov = self._pov_log(battle, entity)
                if pov:
                    lines.append("since last turn:")
                    lines.extend(pov)
            except Exception:
                pass

            lines.append(
                "Task: choose the single best option index from the full list of "
                "actions available this turn. Prefer actions that win the fight "
                "and keep the entity alive."
            )
        except Exception as e:
            logger.debug("[JevPlan] state render failed: %s", e)
            lines.append("State unavailable.")
        return "\n".join(lines)

    def _pov_log(self, battle, entity) -> List[str]:
        """One-line POV summaries of the battle-log entries the entity
        witnessed since the start of its previous turn.

        The window is bounded by the ``last_turn_log_len`` mark ``Battle``
        records in ``start_turn`` (on a first turn it falls back to the whole
        log). Entries are filtered by POV (the entity acted, was targeted,
        or can see the actor/target) and the most recent
        ``MAX_JEV_POV_LOG`` are kept, oldest first.
        """
        start = 0
        try:
            st = battle.entity_state_for(entity)
            if st is not None:
                v = st.get('last_turn_log_len')
                if isinstance(v, int):
                    start = v
        except Exception:
            start = 0
        log = list(getattr(battle, 'battle_log', None) or [])
        start = max(0, min(start, len(log)))
        names = getattr(self, '_names', None)
        out = []
        for action in log[start:]:
            try:
                if not _pov_witnessed(battle, entity, action):
                    continue
                line = _pov_line(action, names)
                if line:
                    out.append("- " + line)
            except Exception:
                continue
        return out[-MAX_JEV_POV_LOG:]

    # -- top level ---------------------------------------------------------- #
    def select(self, battle, entity, available_actions: Optional[List] = None) -> Optional[Any]:
        """Flatten the action space to executable leaves and let JEV pick one."""
        try:
            self._battle = battle
            self._entity = entity
            self._map = battle.map_for(entity)
            self._session = getattr(battle, 'session', None)
            self._decisions = 0
            self._names = self._display_names(battle, entity)
            self._state = self._render_state(battle, entity)

            leaves = self._collect_leaves(available_actions)
            if not leaves:
                return None

            # The whole tree pruned down to a single option: no round-trip.
            # Since pass is always offered, this is the "nothing to do but
            # end the turn" case (the controller turns it into an end turn).
            if len(leaves) == 1:
                logger.debug("[JevPlan] %s single legal option; auto-selecting %r",
                             getattr(entity, 'name', '?'), leaves[0][2])
                return self._enrich(battle, entity, leaves[0][1])

            descs = [d for _, _, d in leaves]
            idx = self._decide(self._state, descs)
            if idx is None:
                return None
            action = leaves[idx][1]
            logger.debug("[JevPlan] %s chose %r", getattr(entity, 'name', '?'), descs[idx])
            return self._enrich(battle, entity, action)
        except Exception as e:
            logger.debug("[JevPlan] planner failed: %s", e)
            return None

    # -- leaf collection ------------------------------------------------------ #
    def _collect_leaves(self, available_actions: Optional[List]) -> List[Tuple[str, Any, str]]:
        """Enumerate fully-specified, currently-executable leaf actions.

        Returns ``[(type_key, action, description)]`` for one flat JEV
        question. Infeasible actions (no weapon, no legal target, no usable
        item/object) are rejected. When ``available_actions`` is supplied
        (the battle loop's pre-built list) it is used directly as the
        authoritative option set (an empty list leaves only the pass option);
        otherwise each valid action class is autobuilt to its leaves and the
        strategic movement leaves are included.

        Every result carries a final ``pass (end turn)`` leaf
        (``EndTurnAction``) so the model can always choose to end the turn
        instead of acting.
        """
        from natural20.utils.action_builder import autobuild

        leaves: List[Tuple[str, Any, str]] = []

        def add(action, desc: Optional[str] = None):
            if action is None or getattr(action, 'disabled', False):
                return
            if not self._is_executable(action):
                return
            t = self._type_key(action)
            if desc is None:
                desc = _leaf_desc(action, getattr(self, '_names', None))
            leaves.append((t, action, desc))

        if available_actions is not None:
            # Battle-loop path: the pre-built list is authoritative (an empty
            # list means nothing is available this turn). Movement is handled
            # separately by the loop's move_for, so raw move actions are
            # skipped here.
            for a in available_actions:
                if self._type_key(a) == 'move':
                    continue
                self._enrich(self._battle, self._entity, a)  # pre-target defaults
                add(a)
            return self._with_pass(self._cap_leaves(leaves))

        # Full auto-build path (move_for / direct planning): movement gets the
        # rich pathfinding treatment alongside the other action classes.
        for action, desc in self._move_leaves():
            add(action, desc)

        session = self._session
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
        return self._with_pass(self._cap_leaves(leaves))

    def _with_pass(self, leaves: List[Tuple[str, Any, str]]) -> List[Tuple[str, Any, str]]:
        """Always offer "pass (end turn)" as the final top-level option.

        Ending the turn is a legal choice on every turn, so the pass leaf is
        appended *after* capping and can never be squeezed out of the list.
        """
        if any(t == 'end_turn' for t, _, _ in leaves):
            return leaves
        from natural20.actions.end_turn_action import EndTurnAction
        try:
            action = EndTurnAction(self._session, self._entity, 'end_turn')
        except Exception:
            return leaves
        return leaves + [('end_turn', action, 'pass (end turn)')]

    def _cap_leaves(self, leaves: List[Tuple[str, Any, str]]) -> List[Tuple[str, Any, str]]:
        """Rank and cap the flat option list for the single JEV question."""
        def hp_key(a):
            t = getattr(a, 'target', None)
            try:
                return (t.hp() or 0) if t is not None else 10 ** 6
            except Exception:
                return 10 ** 6

        by_type: Dict[str, List[Tuple[str, Any, str]]] = {}
        for leaf in leaves:
            by_type.setdefault(leaf[0], []).append(leaf)

        capped: List[Tuple[str, Any, str]] = []
        for t in ('attack', 'spell', 'move'):
            group = by_type.pop(t, [])
            if t in ('attack', 'spell'):
                # Finishers first: prefer the weakest legal target.
                group.sort(key=lambda l: hp_key(l[1]))
            capped.extend(group[:MAX_JEV_OPTIONS])
        for group in by_type.values():
            capped.extend(group[:MAX_JEV_OPTIONS])
        return capped[:MAX_JEV_LEAVES]

    # -- executability filtering ---------------------------------------------- #
    def _is_executable(self, action) -> bool:
        """False if the action cannot be completed in the current battle state.

        Catches the common dead-ends before they reach the decision model:
        weapon attacks with no weapon (unresolvable range), and actions whose
        target tree has no legal target right now. Unknown action types
        default to executable.
        """
        battle = self._battle
        entity = self._entity
        if battle is None or entity is None:
            return True
        try:
            from natural20.actions.attack_action import AttackAction
            from natural20.actions.spell_action import SpellAction
            from natural20.actions.help_action import HelpAction
            from natural20.actions.shove_action import ShoveAction
            from natural20.actions.grapple_action import GrappleAction
            from natural20.actions.interact_action import InteractAction
        except ImportError:
            return True

        try:
            if isinstance(action, AttackAction):
                at = getattr(action, 'action_type', None)
                if at in ('attack', 'two_weapon_attack'):
                    # An attack needs a weapon (or npc_action spec) with a
                    # resolvable range; otherwise valid_targets_for raises.
                    if not (getattr(action, 'npc_action', None)
                            or getattr(action, 'using', None)):
                        return False
                return bool(battle.valid_targets_for(entity, action))
            if isinstance(action, HelpAction):
                if getattr(action, 'target', None) is not None:
                    return True
                return bool(battle.valid_targets_for(entity, action))
            if isinstance(action, (ShoveAction, GrappleAction)):
                # validate() on these has a narrower signature, so
                # valid_targets_for raises; trust an already-built target and
                # otherwise check melee reach manually.
                if getattr(action, 'target', None) is not None:
                    return True
                m = self._map
                if m is None:
                    return True
                return any(
                    (not e.dead()) and e.conscious()
                    and battle.can_see(entity, e)
                    and _dist_ft(battle, m, entity, e) <= 5
                    for e in battle.opponents_of(entity)
                )
            if isinstance(action, SpellAction):
                if getattr(action, 'target', None) is not None:
                    return True
                if battle.valid_targets_for(entity, action):
                    return True
                # No creature in range: still castable when the spell does
                # not require a creature target (empty space, cone, self).
                return not self._spell_requires_creature(action)
            if isinstance(action, InteractAction):
                if getattr(action, 'target', None) is not None:
                    return True
                m = self._map
                if m is None:
                    return True
                return any(not o.dead() for o in m.interactable_objects)
            return True
        except Exception:
            # valid_targets_for raises on unresolvable ranges etc -> dead end.
            return False

    def _spell_requires_creature(self, action) -> bool:
        """True if the spell's parameter tree includes a creature target."""
        sa = getattr(action, 'spell_action', None)
        if sa is None:
            return True
        try:
            node = sa.build_map(action)
            for _ in range(8):
                if not isinstance(node, dict):
                    break
                for p in node.get('param') or []:
                    if p.get('type') == 'select_target':
                        ttypes = [str(t).lower()
                                  for t in (p.get('target_types') or ['enemies'])]
                        if any(t in ('enemies', 'self', 'allies') for t in ttypes):
                            return True
                nxt = node.get('next')
                node = nxt() if callable(nxt) else None
            return False
        except Exception:
            return True

    def _action_classes(self, session):
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.spell_action import SpellAction
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
        # NOTE: MoveAction is deliberately absent: _move_leaves() replaces the
        # builder's raw one-step move leaves with strategic destination leaves.
        return [
            AttackAction, SpellAction, HelpAction, DodgeAction,
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
            from natural20.actions.end_turn_action import EndTurnAction
            if isinstance(action, EndTurnAction):
                return 'end_turn'
            if isinstance(action, AttackAction):
                return 'attack'
            if isinstance(action, SpellAction):
                return 'spell'
            if isinstance(action, MoveAction):
                return 'move'
            if isinstance(action, DashAction):
                return 'dash'
            if isinstance(action, DisengageAction):
                return 'disengage'
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

    # -- move: special strategic handling ----------------------------------- #
    def _move_leaves(self):
        """Yield ``(MoveAction, description)`` for every legal destination.

        Strategic intents (only those currently legal are offered):
          0. engage       close to an enemy so we are in its melee range
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
            return

        pos = m.position_of(ent)
        move_ft = ent.available_movement(battle)
        if move_ft <= 0:
            return

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
                    self._display_name(e)
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
            return

        # Per-option labels for melee ('engage ...') and hide ('hide at ...')
        # already carry the intent keyword; defensive/offensive need it added.
        intent_prefix = {'defensive': 'defensive ', 'offensive': 'offensive '}
        for _intent_label, kind, options, labels in intents:
            logger.debug("[JevPlan] move intent: %s (%d options)", kind, len(options))
            prefix = intent_prefix.get(kind, '')
            for opt, label in zip(options, labels):
                path = opt[1]
                action = MoveAction(self._session, ent, 'move')
                action.move_path = list(path)
                yield action, f"move: {prefix}{label}"

    # -- final enrichment ------------------------------------------------------ #
    def _enrich(self, battle, entity, action) -> Any:
        """Last-ditch defaults if a required param is still unset."""
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.spell_action import SpellAction
        from natural20.actions.help_action import HelpAction
        from natural20.actions.shove_action import ShoveAction
        from natural20.actions.grapple_action import GrappleAction
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
            if getattr(action, 'target', None) is None:
                if isinstance(action, HelpAction):
                    # allies first, then any legal target within reach
                    try:
                        targets = battle.valid_targets_for(entity, action,
                                                           target_types=['allies', 'enemies'])
                    except Exception:
                        targets = []
                    if not targets:
                        targets = battle.valid_targets_for(entity, action)
                    if targets:
                        action.target = sorted(targets, key=lambda t: (t.hp() or 0))[0]
                elif isinstance(action, (ShoveAction, GrappleAction)):
                    targets = battle.valid_targets_for(entity, action,
                                                       target_types=['enemies'], range=5)
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
    """Display name of the spell (``Burning Hands``), not its YAML slug."""
    try:
        sp = getattr(action, 'spell', None) or (getattr(action, 'opts', None) or {}).get('spell')
        if isinstance(sp, dict):
            return sp.get('name') or sp.get('label') or sp.get('slug')
        if isinstance(sp, str):
            return sp
        sa = getattr(action, 'spell_action', None)
        if sa is not None:
            # The spell instance carries the YAML props; ``properties['name']``
            # is the display name (``short_name`` is derived from the slug).
            props = getattr(sa, 'properties', None)
            if isinstance(props, dict):
                if props.get('name') or props.get('label'):
                    return props.get('name') or props.get('label')
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


def _target_name(t, names=None) -> str:
    """Target name with current HP, e.g. ``Gomerin (11/11)``.

    ``names`` (id -> disambiguated display name, see
    ``JevActionPlanner._display_names``) is used when present so targets
    with colliding names stay identifiable.
    """
    if t is None:
        return 'target'
    try:
        base = (names.get(id(t)) if names else None) or _name(t)
        d = t.hp()
        mx = t.max_hp()
        if d is not None and mx is not None:
            return f"{base} ({d}/{mx})"
    except Exception:
        pass
    return _name(t)


def _pov_result_suffix(action) -> str:
    """Compact outcome of a committed action, e.g. ``hit, 7 dmg`` or ``miss``."""
    parts = []
    msg = None
    for item in (getattr(action, 'result', None) or []):
        if not isinstance(item, dict):
            continue
        t = item.get('type')
        if t == 'hit':
            parts.append('hit')
        elif t == 'critical':
            parts.append('critical')
        elif t == 'damage':
            parts.append(f"{item.get('damage', 0)} dmg")
        elif t == 'miss':
            parts.append('miss')
        elif t == 'message' and msg is None:
            m = (item.get('message') or '').strip()
            if m:
                msg = m
    if parts:
        return ', '.join(parts)
    return (msg or '')[:40]


def _pov_targets(action):
    """The action's target(s) as a list (single targets are wrapped)."""
    t = getattr(action, 'target', None)
    if t is None:
        return []
    if isinstance(t, (list, tuple)):
        return [x for x in t if x is not None]
    return [t]


def _pov_witnessed(battle, entity, action) -> bool:
    """POV: did ``entity`` witness this committed battle-log entry?

    Yes if the entity itself acted, was targeted, or can see the actor or a
    target (something happening to a creature in sight is witnessed even
    when the cause is hidden).
    """
    src = getattr(action, 'source', None)
    if src is entity:
        return True
    for t in _pov_targets(action):
        if t is entity:
            return True
        if t is not None and hasattr(t, 'entity_uid'):
            try:
                if battle.can_see(entity, t):
                    return True
            except Exception:
                pass
    if src is not None and src is not entity:
        try:
            return battle.can_see(entity, src)
        except Exception:
            return False
    return False


def _pov_line(action, names=None) -> Optional[str]:
    """One-line POV rendering of a committed battle-log entry.

    Returns ``None`` for entries that carry no POV information (plain
    end-of-turn entries) so they are skipped.
    """
    try:
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.spell_action import SpellAction
        from natural20.actions.move_action import MoveAction
        from natural20.actions.dodge_action import DodgeAction
        from natural20.actions.dash import DashAction
        from natural20.actions.disengage_action import DisengageAction
        from natural20.actions.help_action import HelpAction
        from natural20.actions.hide_action import HideAction
        from natural20.actions.stand_action import StandAction
        from natural20.actions.look_action import LookAction
        from natural20.actions.second_wind_action import SecondWindAction
        from natural20.actions.use_item_action import UseItemAction
        from natural20.actions.interact_action import InteractAction
        from natural20.actions.shove_action import ShoveAction
        from natural20.actions.grapple_action import GrappleAction
        from natural20.actions.end_turn_action import EndTurnAction

        src = getattr(action, 'source', None)
        if src is None or isinstance(action, EndTurnAction):
            return None
        actor = (names.get(id(src)) if names else None) or _name(src)
        if isinstance(action, AttackAction):
            line = f"{actor} attacked {_target_name(action.target, names)}"
        elif isinstance(action, SpellAction):
            s = _spell_name(action) or 'a spell'
            ts = [t for t in _pov_targets(action)
                  if hasattr(t, 'name') and not isinstance(t, (list, tuple))]
            line = f"{actor} cast {s}"
            if ts:
                line += " on " + ", ".join(_target_name(t, names) for t in ts[:2])
        elif isinstance(action, MoveAction):
            line = f"{actor} moved"
        elif isinstance(action, DashAction):
            line = f"{actor} dashed"
        elif isinstance(action, DisengageAction):
            line = f"{actor} disengaged"
        elif isinstance(action, DodgeAction):
            line = f"{actor} dodged"
        elif isinstance(action, HelpAction):
            line = f"{actor} helped {_target_name(action.target, names)}"
        elif isinstance(action, HideAction):
            line = f"{actor} hid"
        elif isinstance(action, StandAction):
            line = f"{actor} stood ready"
        elif isinstance(action, LookAction):
            line = f"{actor} looked around"
        elif isinstance(action, SecondWindAction):
            line = f"{actor} used second wind"
        elif isinstance(action, UseItemAction):
            ti = getattr(action, 'target_item', None)
            iname = (getattr(ti, 'name', None) or 'an item') if ti is not None else 'an item'
            t = getattr(action, 'target', None)
            line = f"{actor} used {iname}"
            if t is not None and t is not src and hasattr(t, 'name'):
                line += f" on {_target_name(t, names)}"
        elif isinstance(action, InteractAction):
            t = getattr(action, 'target', None)
            line = f"{actor} interacted with {(_name(t) if t is not None else 'something')}"
        elif isinstance(action, ShoveAction):
            line = f"{actor} shoved {_target_name(action.target, names)}"
        elif isinstance(action, GrappleAction):
            line = f"{actor} grappled {_target_name(action.target, names)}"
        else:
            at = str(getattr(action, 'action_type', 'acted') or 'acted').replace('_', ' ')
            line = f"{actor} {at}"
        suffix = _pov_result_suffix(action)
        if suffix:
            line += f", {suffix}"
        return line
    except Exception:
        return None


def _leaf_desc(action, names=None) -> str:
    """One-line description of a fully-built leaf action (JEV criterion)."""
    from natural20.actions.attack_action import AttackAction
    from natural20.actions.spell_action import SpellAction
    from natural20.actions.move_action import MoveAction
    from natural20.actions.dodge_action import DodgeAction
    from natural20.actions.dash import DashAction
    from natural20.actions.disengage_action import DisengageAction
    from natural20.actions.end_turn_action import EndTurnAction
    try:
        # Class-based names: some builders set a misleading action_type
        # (e.g. DodgeAction/DashAction carry action_type='attack').
        if isinstance(action, EndTurnAction):
            return 'pass (end turn)'
        for cls, name in ((DodgeAction, 'dodge'), (DashAction, 'dash'),
                          (DisengageAction, 'disengage')):
            if isinstance(action, cls):
                return name
        if isinstance(action, AttackAction):
            w = _weapon_name(action) or 'weapon'
            t = getattr(action, 'target', None)
            return f"attack {_target_name(t, names)} with {w}"
        if isinstance(action, SpellAction):
            s = _spell_name(action) or 'spell'
            t = getattr(action, 'target', None)
            tn = _target_name(t, names)
            lvl = getattr(action, 'at_level', None) or getattr(action, 'level', None)
            lvl_txt = '' if lvl else ' (cantrip)'
            lvl_txt = f' (level {lvl})' if lvl else lvl_txt
            return f"cast {s}{lvl_txt} on {tn}"
        if isinstance(action, MoveAction):
            p = getattr(action, 'move_path', None)
            end = p[-1] if p else None
            return f"move to {tuple(end) if end else '?'}"
        ti = getattr(action, 'target_item', None)
        if ti is not None:
            iname = getattr(ti, 'name', None) or 'item'
            t = getattr(action, 'target', None)
            if t is not None and t is not getattr(action, 'source', None):
                return f"use {iname} on {_target_name(t, names)}"
            return f"use {iname}"
        t = getattr(action, 'target', None)
        if t is not None:
            return f"{action.action_type} {_target_name(t, names)}"
        return str(getattr(action, 'action_type', 'action')).replace('_', ' ')
    except Exception:
        return str(getattr(action, 'action_type', 'action'))


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #

def jev_select_action(provider, battle, entity,
                      available_actions: Optional[List] = None,
                      max_decisions: int = DEFAULT_MAX_DECISIONS) -> Optional[Any]:
    """Plan an action with the JEV decision model (one flattened call).

    The action space is flattened to executable leaf actions; single-leaf
    trees are auto-selected without consulting the model. Returns a
    fully-parameterized ``Action`` or ``None`` (caller should then fall back
    to heuristic selection).
    """
    if provider is None or not getattr(provider, 'is_available', False):
        return None
    planner = JevActionPlanner(provider, max_decisions=max_decisions)
    return planner.select(battle, entity, available_actions)
