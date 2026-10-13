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
MAX_JEV_EARLIER_LOG = 12  # witnessed lines from before the entity's last turn
MAX_JEV_HEARD = 8      # in-battle speech lines
MAX_JEV_CONVERSATION = 4  # pre-battle conversation memory lines
# State text budget (N20_JEV_STATE_MAX_CHARS); history is trimmed first.
DEFAULT_JEV_STATE_MAX_CHARS = 6000
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
                if getattr(d.get('effect'), 'ends_at_start_of_turn', False):
                    out.append(f"{name} (until the start of its next turn)")
                elif exp is not None:
                    out.append(f"{name} {max(0, int(exp - now))}s")
                else:
                    out.append(name)
            except Exception:
                continue
    return out


def _conditions(battle, e) -> List[str]:
    """Sheet conditions plus per-turn battle markers (dodging, disengaged)."""
    out: List[str] = []
    try:
        out.extend(c.lower() for c in e.sheet_conditions())
    except Exception:
        out.extend(str(s) for s in (getattr(e, 'statuses', None) or []))
    try:
        st = battle.entity_state_for(e) if battle is not None else None
        for s in ((st or {}).get('statuses') or ()):
            s = 'dodging' if s == 'dodge' else str(s)
            if s not in out:
                out.append(s)
    except Exception:
        pass
    return [c for c in out if c and c != 'dead']


def _creature_details(battle, e, include_conditions: bool = True) -> str:
    """Conditions, concentration, Mirror Image, dying state and damage
    defenses of a creature, as a short comma list."""
    parts = list(_conditions(battle, e)) if include_conditions else []
    try:
        conc = e.current_concentration()
        if conc is not None:
            parts.append(f"concentrating on {_effect_name(conc) or 'a spell'}")
    except Exception:
        pass
    try:
        from natural20.spell.mirror_image_spell import MirrorImageSpell
        images = MirrorImageSpell.images_remaining_for(e)
        if images:
            parts.append(f"{images} mirror image duplicates")
    except Exception:
        pass
    try:
        if e.unconscious() and not e.dead():
            if e.stable():
                parts.append("stable")
            else:
                parts.append(f"dying (death saves {getattr(e, 'death_saves', 0)} ok / "
                             f"{getattr(e, 'death_fails', 0)} failed)")
    except Exception:
        pass
    try:
        temp = int(e.temp_hp() or 0)
        if temp:
            parts.append(f"{temp} temp hp")
    except Exception:
        pass
    try:
        from natural20.utils.monster_traits import regeneration_config
        regen = regeneration_config(e)
        if regen and regen['hp'] > 0 and not e.dead():
            text = f"regenerates {regen['hp']} hp each turn"
            if regen['suppressed_by']:
                text += f" unless it took {'/'.join(regen['suppressed_by'])} damage since its last turn"
            suppressed = (getattr(e, 'attributes', None) or {}).get('regeneration_suppressed')
            if suppressed:
                text += f" (blocked next turn: took {suppressed})"
            parts.append(text)
    except Exception:
        pass
    try:
        d = e.sheet_defenses() or {}
        for key, label in (('resistances', 'resists'), ('immunities', 'immune'),
                           ('vulnerabilities', 'vulnerable')):
            if d.get(key):
                parts.append(f"{label} {'/'.join(str(x) for x in d[key][:4])}")
    except Exception:
        pass
    return ", ".join(parts)


def _self_context_lines(battle, entity) -> List[str]:
    """Round, turn order, and the actor's own reaction / limited resources."""
    lines: List[str] = []
    try:
        order = [e for e in (getattr(battle, 'combat_order', None) or []) if not e.dead()]
        if order:
            names = ['(you)' if e is entity else _name(e) for e in order]
            lines.append(f"round {int(getattr(battle, 'round', 0) or 0) + 1}; turn order: " + " > ".join(names))
    except Exception:
        pass
    res = []
    try:
        st = battle.entity_state_for(entity) or {}
        if 'reaction' in st:
            res.append(f"reaction {'ready' if st.get('reaction') else 'used'}")
    except Exception:
        pass
    for attr, label in (('action_surge_count', 'action surge'), ('second_wind_count', 'second wind')):
        val = getattr(entity, attr, None)
        if isinstance(val, int):
            res.append(f"{label} {val} left")
    try:
        from natural20.utils.monster_traits import legendary_resistance_max, legendary_resistance_remaining
        if legendary_resistance_max(entity):
            res.append(f"legendary resistance {legendary_resistance_remaining(entity)}/"
                       f"{legendary_resistance_max(entity)}")
    except Exception:
        pass
    if res:
        lines.append("own resources: " + ", ".join(res))
    details = _creature_details(battle, entity, include_conditions=False)
    if details:
        lines.append("own state: " + details)
    return lines


def _unseen_enemy_lines(battle, entity, map_, name_fn) -> List[str]:
    """Enemies the actor can't see but has heard or remembers."""
    out: List[str] = []
    try:
        from natural20.utils.unseen_targets import sensed_creatures, KIND_HEARD
        sensed = sensed_creatures(battle, entity)
    except Exception:
        return out
    for entry in sensed:
        try:
            creature = battle.entity_by_uid(entry['uid'])
            if creature is None or creature.dead() or not battle.opposing(entity, creature):
                continue
            pos = list(entry['pos'])
            dist = None
            if map_ is not None:
                dist = int(map_.distance_to_square(entity, pos[0], pos[1]) * (map_.feet_per_grid or 5))
            if entry.get('kind') == KIND_HEARD:
                where = f"heard at {pos}"
            else:
                ago = int(getattr(battle, 'round', 0) or 0) - int(entry.get('round') or 0)
                when = "this round" if ago <= 0 else f"{ago} round{'s' if ago > 1 else ''} ago"
                where = f"last known at {pos} ({when}, may have moved)"
            line = f"{name_fn(creature)} {where}"
            if dist is not None:
                line += f" {dist} ft"
            out.append(line)
        except Exception:
            continue
    return out


def _ally_lines(battle, entity, map_, name_fn) -> List[str]:
    """Every ally in the fight, including those out of sight, down or dead."""
    out: List[str] = []
    fallen = []
    try:
        allies = [a for a in (list(battle.entities.keys()) + list(getattr(battle, 'late_comers', []) or []))
                  if a is not entity and battle.allies(a, entity)]
    except Exception:
        allies = []
    for a in allies:
        try:
            if a.dead():
                fallen.append(name_fn(a))
                continue
            ac = _ac_value(a)
            dist = _dist_ft(battle, map_, entity, a)
            line = f"{name_fn(a)} hp {_hp_text(a)}" + (f" ac {ac}" if ac is not None else "")
            if dist is not None:
                line += f" {dist} ft"
            if not battle.can_see(entity, a):
                line += " (out of sight)"
            details = _creature_details(battle, a)
            if details:
                line += f" [{details}]"
            out.append(line)
        except Exception:
            continue
    if fallen:
        out.append("fallen: " + ", ".join(fallen))
    return out


def _fight_summary(battle, entity, name_fn) -> str:
    """Damage dealt to each enemy so far (and how much of it was ours)."""
    totals: Dict[Any, List[int]] = {}
    for action in (getattr(battle, 'battle_log', None) or []):
        for item in (getattr(action, 'result', None) or []):
            try:
                target = item.get('target')
                dmg = item.get('damage')
                if target is None or dmg is None or not hasattr(target, 'entity_uid'):
                    continue
                if not battle.opposing(entity, target):
                    continue
                if item.get('type') not in ('damage', 'spell_damage'):
                    continue
                value = dmg.result() if hasattr(dmg, 'result') else int(dmg)
                if value <= 0:
                    continue
                bucket = totals.setdefault(target, [0, 0])
                bucket[0] += value
                if item.get('source') is entity:
                    bucket[1] += value
            except Exception:
                continue
    parts = []
    for target, (total, mine) in totals.items():
        part = f"{name_fn(target)} {total}"
        if mine:
            part += f" ({mine} by you)"
        try:
            if target.dead():
                part += " (dead)"
        except Exception:
            pass
        parts.append(part)
    return ", ".join(parts)


def _conversation_lines(entity) -> List[str]:
    """Most recent things said to/around the actor (its memory buffer)."""
    out: List[str] = []
    for entry in list(getattr(entity, 'memory_buffer', None) or [])[-MAX_JEV_CONVERSATION:]:
        try:
            src = entry.get('source')
            if src is entity:
                who = 'you'
            else:
                who = _name(src) if src is not None else 'someone'
            msg = str(entry.get('message') or '').strip().replace('\n', ' ')
            if not msg:
                continue
            lang = str(entry.get('language') or 'common').lower()
            if src is not entity and lang != 'common':
                try:
                    known = [str(l).lower() for l in (entity.languages_understood() or [])]
                    if known and lang not in known:
                        msg = f"(speaks in {lang}; you don't understand)"
                except Exception:
                    pass
            if len(msg) > 140:
                msg = msg[:137] + '...'
            out.append(f"{who}: {msg}")
        except Exception:
            continue
    return out


_TRIM_ORDER = ('earlier in this fight:', 'earlier conversation:', 'heard in this fight:', 'since last turn:')


def _fit_state(lines: List[str]) -> str:
    """Join state lines within ``N20_JEV_STATE_MAX_CHARS``, dropping the
    oldest history first (then conversation, speech, recent events)."""
    import os
    try:
        budget = int(os.environ.get('N20_JEV_STATE_MAX_CHARS') or DEFAULT_JEV_STATE_MAX_CHARS)
    except ValueError:
        budget = DEFAULT_JEV_STATE_MAX_CHARS
    lines = list(lines)
    for header in _TRIM_ORDER:
        while len("\n".join(lines)) > budget and header in lines:
            i = lines.index(header)
            if i + 1 < len(lines) and lines[i + 1].startswith('- '):
                del lines[i + 1]
            else:
                del lines[i]
    text = "\n".join(lines)
    if len(text) <= budget or not lines:
        return text
    task = lines[-1]
    head = "\n".join(lines[:-1])[:max(0, budget - len(task) - 1)]
    return head + "\n" + task


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
                in_melee = now
        return False
    except Exception:
        return False


def _attack_odds_text(battle, action) -> str:
    """`` [disadvantage: ranged_with_enemy_in_melee; 45% hit, ~9 dmg]`` for a
    targeted attack, so the model can compare weapons (a bow at disadvantage
    in melee vs. a rapier)."""
    target = getattr(action, 'target', None)
    if battle is None or target is None or not hasattr(target, 'entity_uid'):
        return ""
    from natural20.utils.unseen_targets import makes_attack_roll
    if not makes_attack_roll(action):
        return " [no attack roll; the target saves]"
    parts = []
    try:
        mod, info, _ = action.compute_advantage_info(battle)
        adv, dis = (info or [[], []])[:2]
        if mod > 0:
            parts.append("advantage: " + ", ".join(str(a) for a in adv))
        elif mod < 0:
            parts.append("disadvantage: " + ", ".join(str(d) for d in dis))
    except Exception:
        pass
    try:
        parts.append(f"{int(round(action.compute_hit_probability(battle) * 100))}% hit")
        parts.append(f"~{int(round(action.avg_damage(battle)))} dmg")
    except Exception:
        pass
    try:
        from natural20.utils.pointless_actions import _downed
        if action.target is not None and _downed(action.target):
            parts.append("target is already down: a hit only adds death save failures")
    except Exception:
        pass
    return f" [{'; '.join(parts)}]" if parts else ""


_SPELLCASTER_CLASSES = {'wizard', 'sorcerer', 'warlock', 'bard', 'cleric', 'druid'}


def _ranged_combatant(entity) -> bool:
    """True for characters who fight mainly with spells (most of their levels
    in a full-caster class), so ending a turn in melee only invites attacks."""
    classes = (getattr(entity, 'properties', None) or {}).get('classes')
    if not isinstance(classes, dict) or not classes:
        return False
    try:
        total = sum(int(v or 0) for v in classes.values())
        casting = sum(int(v or 0) for k, v in classes.items() if str(k).lower() in _SPELLCASTER_CLASSES)
    except (TypeError, ValueError):
        return False
    return total > 0 and casting * 2 > total


def _multiattack_follow_up_available(action_class, entity, battle) -> bool:
    """Once the first attack of a Multiattack spends the action, the class-level
    ``AttackAction.can`` is False; the remaining attacks are only allowed
    per ``npc_action``."""
    from natural20.actions.attack_action import AttackAction
    if action_class is not AttackAction or battle is None:
        return False
    for spec in getattr(entity, 'npc_actions', None) or []:
        if isinstance(spec, dict) and spec.get('multiattack_group') \
                and AttackAction.can(entity, battle, {'npc_action': spec}):
            return True
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
                from natural20.utils.grappling import grapple_status_text
                grapple_txt = grapple_status_text(entity)
                if grapple_txt:
                    lines.append(grapple_txt)
            except Exception:
                pass
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

            lines.extend(_self_context_lines(battle, entity))

            enemies = [e for e in battle.opponents_of(entity) if battle.can_see(entity, e) and not e.dead()]
            elines = []
            for e in enemies:
                d = _dist_ft(battle, m, entity, e)
                ac = _ac_value(e)
                ac_part = f" ac {ac}" if ac is not None else ""
                details = _creature_details(battle, e)
                down = ""
                try:
                    if e.incapacitated():
                        down = " (unconscious)" if e.unconscious() else " (incapacitated)"
                except Exception:
                    pass
                elines.append(f"{self._display_name(e)} hp {_hp_text(e)}{ac_part} {d} ft"
                              + (" melee" if (d or 99) <= 5 else "") + down
                              + (f" [{details}]" if details else ""))
            lines.append("visible enemies: " + ("; ".join(elines) or "none"))
            unseen = _unseen_enemy_lines(battle, entity, m, self._display_name)
            if unseen:
                lines.append("unseen enemies (not visible; attack their square at disadvantage, "
                             "or use area spells): " + "; ".join(unseen))

            lines.append("allies: " + ("; ".join(_ally_lines(battle, entity, m, self._display_name)) or "none"))

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

            try:
                from natural20.utils.combat_intelligence import tactics_tier, intelligence_score
                lines.append(f"tactics: {tactics_tier(entity)} (INT {intelligence_score(entity)})")
            except Exception:
                pass

            try:
                summary = _fight_summary(battle, entity, self._display_name)
                if summary:
                    lines.append("damage dealt so far: " + summary)
            except Exception:
                pass

            heard = []
            try:
                from natural20.utils.combat_comms import callout_lines
                heard = callout_lines(battle, entity, max_lines=MAX_JEV_HEARD)
            except Exception:
                pass
            heard_text = " ".join(heard)
            convo = [c for c in _conversation_lines(entity) if c.split(': ', 1)[-1] not in heard_text]
            if heard:
                lines.append("heard in this fight:")
                lines.extend("- " + h for h in heard)
            if convo:
                lines.append("earlier conversation:")
                lines.extend("- " + c for c in convo)

            # POV: what the entity witnessed earlier and since its last turn
            try:
                earlier, recent = self._pov_history(battle, entity)
                if earlier:
                    lines.append("earlier in this fight:")
                    lines.extend(earlier)
                if recent:
                    lines.append("since last turn:")
                    lines.extend(recent)
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
        return _fit_state(lines)

    def _pov_history(self, battle, entity) -> Tuple[List[str], List[str]]:
        """``(earlier, since_last_turn)`` witnessed battle-log lines. The
        earlier window covers the fight before the entity's previous turn."""
        start = len(getattr(battle, 'battle_log', None) or [])
        try:
            st = battle.entity_state_for(entity)
            v = st.get('last_turn_log_len') if st is not None else None
            if isinstance(v, int):
                start = v
            else:
                start = 0
        except Exception:
            start = 0
        log = list(getattr(battle, 'battle_log', None) or [])
        start = max(0, min(start, len(log)))
        names = getattr(self, '_names', None)
        earlier = []
        for action in log[:start]:
            try:
                if _pov_witnessed(battle, entity, action):
                    line = _pov_line(action, names)
                    if line:
                        earlier.append("- " + line)
            except Exception:
                continue
        return earlier[-MAX_JEV_EARLIER_LOG:], self._pov_log(battle, entity)

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
                if t == 'attack':
                    desc += _attack_odds_text(self._battle, action)
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
            return self._with_pass(self._cap_leaves(self._skirmish_filter(leaves)))

        # Full auto-build path (move_for / direct planning): movement gets the
        # rich pathfinding treatment alongside the other action classes.
        for action, desc in self._move_leaves():
            add(action, desc)

        from natural20.actions.spell_action import SpellAction
        session = self._session
        allowed = self._allowed_action_classes(session)
        for klass in self._action_classes(session):
            if allowed is not None and klass not in allowed:
                continue
            follow_ups_only = False
            try:
                if not _class_can(klass, self._entity, self._battle):
                    if not _multiattack_follow_up_available(klass, self._entity, self._battle):
                        continue
                    follow_ups_only = True
            except Exception:
                continue
            try:
                built = autobuild(session, klass, self._entity, self._battle,
                                  map=self._map, auto_target=False)
                if follow_ups_only:
                    built = [a for a in built
                             if klass.can(self._entity, self._battle,
                                          {'npc_action': getattr(a, 'npc_action', None)})]
                if klass is SpellAction:
                    built = self._optimize_area_spells(built)
            except Exception:
                continue
            for a in built:
                add(a)
        for a in self._variant_leaves(session, allowed):
            add(a)
        from natural20.utils.unseen_targets import base_attack_actions, blind_attack_variants
        try:
            for a in blind_attack_variants(self._battle, self._entity,
                                           base_attack_actions(session, self._entity, self._battle)):
                add(a)
        except Exception:
            pass
        from natural20.actions.summon_creatures_action import SummonCreaturesAction
        for a in SummonCreaturesAction.options_for(session, self._entity, self._battle):
            add(a)
        return self._with_pass(self._cap_leaves(self._skirmish_filter(leaves)))

    def _skirmish_filter(self, leaves: List[Tuple[str, Any, str]]) -> List[Tuple[str, Any, str]]:
        """Shoot-and-hide tactics for creatures with a bonus-action Hide
        (Cunning Action, Nimble Escape): with a ranged shot available, don't
        walk into melee, and point out hiding after the shot."""
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.hide_action import HideAction
        try:
            if not self._entity.any_class_feature(['cunning_action', 'nimble_escape']):
                return leaves
        except Exception:
            return leaves

        def ranged_shot(a):
            try:
                return (isinstance(a, AttackAction) and getattr(a, 'target', None) is not None
                        and a.ranged_attack())
            except Exception:
                return False

        has_shot = any(ranged_shot(a) for _, a, _ in leaves)
        out = []
        for t, a, d in leaves:
            if has_shot and t == 'move' and (d.startswith('move: engage') or d.startswith('move: offensive')):
                continue
            if isinstance(a, HideAction) and getattr(a, 'as_bonus_action', False):
                d = f"{d} (bonus action: hide after shooting so your next attack has advantage)"
            out.append((t, a, d))
        return out

    def _optimize_area_spells(self, built: List[Any]) -> List[Any]:
        """Replace per-square variants of AoE spells with the builder's best anchor.

        Unoptimized autobuild yields one leaf per square in range (Fireball
        alone can produce hundreds), which crowds every other spell out of
        the capped option list. The ``auto_target=True`` builder keeps only
        the square that hits the most enemies and fewest allies (or none
        when no square is worth it). Creature-targeted spells keep their
        per-target leaves.
        """
        from natural20.utils.action_builder import autobuild
        from natural20.actions.spell_action import SpellAction

        point_keys = {_spell_key(a) for a in built if _is_point_target(getattr(a, 'target', None))}
        if not point_keys:
            return built
        optimized = autobuild(self._session, SpellAction, self._entity, self._battle,
                              map=self._map, auto_target=True)
        result = [a for a in built if _spell_key(a) not in point_keys]
        result.extend(a for a in optimized if _spell_key(a) in point_keys)
        return result

    def _with_pass(self, leaves: List[Tuple[str, Any, str]]) -> List[Tuple[str, Any, str]]:
        """Always offer "pass (end turn)" as the final top-level option.

        Ending the turn is a legal choice on every turn, so the pass leaf is
        appended *after* capping and can never be squeezed out of the list.
        """
        if any(t == 'end_turn' for t, _, _ in leaves):
            return leaves
        if self._dash_unspent() and any(t == 'move' for t, _, _ in leaves):
            # The Dash bought movement for a destination: passing now wastes it.
            return leaves
        from natural20.actions.end_turn_action import EndTurnAction
        try:
            action = EndTurnAction(self._session, self._entity, 'end_turn')
        except Exception:
            return leaves
        return leaves + [('end_turn', action, 'pass (end turn)')]

    def _dash_unspent(self) -> bool:
        """The creature Dashed this turn and still has the extra movement."""
        try:
            ent, battle = self._entity, self._battle
            return (ent.available_movement(battle) or 0) > (ent.speed() or 0)
        except Exception:
            return False

    def _cap_leaves(self, leaves: List[Tuple[str, Any, str]]) -> List[Tuple[str, Any, str]]:
        """Rank and cap the flat option list for the single JEV question.

        Instinct-tier creatures (INT 1-3) only keep hostile options aimed at
        the nearest enemy or their last attacker (``combat_intelligence``).
        """
        try:
            from natural20.utils import friendly_fire
            leaves = friendly_fire.filter_actions(self._battle, self._entity, leaves,
                                                  action_of=lambda leaf: leaf[1])
        except Exception:
            pass
        try:
            from natural20.utils import pointless_actions
            leaves = pointless_actions.filter_actions(self._battle, self._entity, leaves,
                                                      action_of=lambda leaf: leaf[1])
        except Exception:
            pass
        try:
            from natural20.utils.combat_intelligence import filter_actions
            leaves = filter_actions(self._battle, self._entity, leaves, target_of=lambda leaf: leaf[1])
        except Exception:
            pass

        def hp_key(a):
            t = getattr(a, 'target', None)
            members = t if isinstance(t, (list, tuple)) else [t]
            hps = []
            for m in members:
                try:
                    if hasattr(m, 'hp'):
                        hps.append(m.hp() or 0)
                except Exception:
                    continue
            return min(hps) if hps else 10 ** 6

        by_type: Dict[str, List[Tuple[str, Any, str]]] = {}
        for leaf in leaves:
            by_type.setdefault(leaf[0], []).append(leaf)

        capped: List[Tuple[str, Any, str]] = []
        for t in ('attack', 'spell', 'move'):
            group = by_type.pop(t, [])
            if t in ('attack', 'spell'):
                # Finishers first: prefer the weakest legal target.
                group.sort(key=lambda l: hp_key(l[1]))
            if t == 'spell':
                group = _round_robin_by_spell(group)
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
                square = getattr(action, 'target_square', None)
                if square is not None and getattr(action, 'target', None) is None:
                    from natural20.utils.unseen_targets import blind_attack_issue
                    return blind_attack_issue(battle, entity, action, tuple(square)) is None
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
                if getattr(action, 'spell_action', None) is None:
                    return False
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

    def _allowed_action_classes(self, session):
        """Action classes the entity may currently use, per ``available_actions``.

        The auto-build path builds classes directly, so it must honor the same
        gating (polymorph / Wild Shape forms can't cast spells, etc.). Returns
        None when the list can't be computed.
        """
        try:
            options = self._entity.available_actions(session, self._battle, auto_target=False,
                                                     map=self._map)
        except TypeError:
            options = self._entity.available_actions(session, self._battle, auto_target=False)
        except Exception:
            return None
        return {type(a) for a in options}

    def _variant_leaves(self, session, allowed):
        """Options whose class specializes one of ``_action_classes`` (a beast
        form's attacks, Cunning Action's bonus-action Hide/Dash/Disengage)."""
        if not allowed:
            return []
        known = set(self._action_classes(session))
        extra = {cls for cls in allowed
                 if cls not in known and any(issubclass(cls, k) for k in known)}
        if not extra:
            return []
        try:
            options = self._entity.available_actions(session, self._battle)
        except Exception:
            return []
        # Blind-attack variants are added separately by the caller.
        return [a for a in options
                if type(a) in extra and getattr(a, 'target_square', None) is None]

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
        from natural20.actions.action_surge_action import ActionSurgeAction
        # NOTE: MoveAction is deliberately absent: _move_leaves() replaces the
        # builder's raw one-step move leaves with strategic destination leaves.
        return [
            AttackAction, SpellAction, HelpAction, DodgeAction,
            HideAction, DashAction, DisengageAction, StandAction, LookAction,
            SecondWindAction, UseItemAction, InteractAction, ShoveAction,
            GrappleAction, ActionSurgeAction,
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
            from natural20.actions.action_surge_action import ActionSurgeAction
            if isinstance(action, EndTurnAction):
                return 'end_turn'
            if isinstance(action, ActionSurgeAction):
                return 'action_surge'
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

        # Each move_for call is a fresh decision; without this a creature with
        # movement left steps back and forth between the same squares.
        try:
            state = battle.entity_state_for(ent) or {}
            visited = {tuple(p) for p in state.get('positions_entered') or {}}
            if state.get('turn_start_position'):
                visited.add(tuple(state['turn_start_position']))
        except Exception:
            visited = set()

        # Provoking an opportunity attack is only worth it to flee when hurt.
        try:
            fleeing = ent.hp() <= ent.max_hp() / 2
        except Exception:
            fleeing = False
        try:
            action_spent = (ent.total_actions(battle) or 0) <= 0
        except Exception:
            action_spent = False
        try:
            engaged = any(
                m.distance(ent, e) * (getattr(m, 'feet_per_grid', 5) or 5) <= (ent.melee_distance() or 5)
                for e in battle.opponents_of(ent)
                if not e.dead() and e.conscious() and battle.can_see(ent, e))
        except Exception:
            engaged = False
        caster = _ranged_combatant(ent)
        try:
            skirmisher = bool(ent.any_class_feature(['cunning_action', 'nimble_escape']))
        except Exception:
            skirmisher = False
        # Already in melee with no action left: shuffling around the foe gains
        # nothing. A spellcaster or shoot-and-hide skirmisher with its action
        # spent has no reason to walk into melee at all - that only invites
        # attacks.
        reposition_pointless = action_spent and (engaged or caster or skirmisher)
        disengaged = False
        try:
            disengaged = bool(ent.disengage(battle))
        except Exception:
            pass
        # A caster or skirmisher stuck in melee is better off taking one
        # opportunity attack to get clear than standing in reach all round.
        oa_retreat_ok = engaged and not disengaged and (caster or skirmisher)

        def dest_ok(dest, path, allow_oa=False):
            if not path or len(path) < 2:
                return False
            end = tuple(path[-1])
            if end in visited:
                return False
            if not (fleeing or allow_oa) and _oa_risk(battle, ent, path):
                return False
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
            reach_ft = ent.melee_distance() or 5
            for e in enemies:
                epos = m.position_of(e)
                if m.distance(ent, e) * (getattr(m, 'feet_per_grid', 5) or 5) <= reach_ft:
                    continue
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

        # ---- intent 0b: advance toward a foe too far to reach this turn ---- #
        approach = []
        if not reposition_pointless:
            try:
                approach = self._approach_options(m, ent, battle, pos, move_ft, pc_calc, dest_ok, caster)
            except Exception:
                approach = []

        # ---- intent 1/3: defensive & offensive squares ---- #
        def candidate_squares(allow_oa=False):
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
                    if not dest_ok(cand, p, allow_oa):
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
        retreat = []
        feet = getattr(m, 'feet_per_grid', 5) or 5
        try:
            enemies = [e for e in battle.opponents_of(ent)
                       if battle.can_see(ent, e) and not e.dead() and e.conscious()]
            current_gap = min((m.distance(ent, e) * feet for e in enemies), default=None)
            # Step out of reach: when engaged, after Disengage, or a caster
            # standing too close to a foe.
            dashed = False
            try:
                dashed = move_ft > (ent.speed() or 0)
            except Exception:
                pass
            want_retreat = bool(enemies) and (
                engaged or disengaged or fleeing or dashed
                or (caster and current_gap is not None and current_gap <= 10))

            def out_of_reach(cand):
                return all(m.distance(ent, e, entity_1_pos=cand) * feet > (e.melee_distance() or 5)
                           for e in enemies)

            for cand, p in candidate_squares(allow_oa=oa_retreat_ok):
                oa = _oa_risk(battle, ent, p)
                if want_retreat and out_of_reach(cand) and (not oa or fleeing or oa_retreat_ok):
                    gap = min(m.distance(ent, e, entity_1_pos=cand) * feet for e in enemies)
                    if engaged or current_gap is None or gap > current_gap:
                        retreat.append((cand, p, gap, oa))
                if oa and not fleeing:
                    continue
                cover = 'none'
                try:
                    cover = m.cover_at(cand[0], cand[1], origin=pos) or 'none'
                except Exception:
                    pass
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
        if reposition_pointless:
            melee_uniq = []
            offensive = []
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
        if approach:
            intents.append(("advance toward an enemy that is out of reach this turn", 'approach',
                            [(cand, p) for cand, p, _ in approach], [label for _, _, label in approach]))
        if retreat:
            retreat.sort(key=lambda x: (x[3], -x[2], len(x[1])))
            picks = retreat[:min(4, MAX_JEV_OPTIONS)]
            labels = [f"retreat to {cand} (out of reach, "
                      f"{'provokes an opportunity attack, ' if oa else ''}{int(gap)} ft from nearest foe)"
                      for cand, p, gap, oa in picks]
            intents.append(("step out of enemy reach", 'retreat',
                            [(cand, p) for cand, p, _, _ in picks], labels))
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

    def _approach_options(self, m, ent, battle, pos, move_ft, pc_calc, dest_ok, caster):
        """``(square, path, label)`` moves that close on the nearest foes when
        no melee square is reachable this turn. Falls back to heard /
        last-known squares of unseen foes, then to downed foes."""
        feet = getattr(m, 'feet_per_grid', 5) or 5
        reach = (ent.melee_distance() or 5)
        visible = [e for e in battle.opponents_of(ent)
                   if not e.dead() and battle.can_see(ent, e) and m.position_of(e) is not None]
        up = [e for e in visible if e.conscious()]
        if caster and any(m.distance(ent, e) * feet <= 60 for e in up):
            return []
        goals = []  # (label name, square)
        for e in sorted(up, key=lambda e: m.distance(ent, e)):
            if m.distance(ent, e) * feet <= reach + move_ft:
                continue  # engage already covers a reachable foe
            goals.append((self._display_name(e), tuple(m.position_of(e))))
        if not up:
            try:
                from natural20.utils.unseen_targets import sensed_creatures
                for entry in sensed_creatures(battle, ent):
                    foe = battle.entity_by_uid(entry['uid'])
                    if foe is not None and battle.opposing(ent, foe) and not foe.dead():
                        goals.append((f"{self._display_name(foe)}'s {entry.get('kind', 'last known').replace('_', ' ')} position",
                                      tuple(entry['pos'])))
            except Exception:
                pass
            if not goals:
                goals = [(f"downed {self._display_name(e)}", tuple(m.position_of(e)))
                         for e in sorted(visible, key=lambda e: m.distance(ent, e))]
        steps = int(move_ft // feet)
        out = []
        for name, goal in goals[:3]:
            full = None
            best = None
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    cand = (goal[0] + dx, goal[1] + dy)
                    if (dx or dy) and _in_battle(m, *cand) and m.placeable(ent, *cand, battle):
                        d = abs(cand[0] - pos[0]) + abs(cand[1] - pos[1])
                        if best is None or d < best[0]:
                            best = (d, cand)
            if best is None:
                continue
            try:
                full = pc_calc.compute_path(pos[0], pos[1], best[1][0], best[1][1])
            except Exception:
                full = None
            if not full or len(full) < 2:
                continue
            sub = list(full[:steps + 1])
            path = None
            while len(sub) >= 2:
                try:
                    path = pc_calc.compute_path(pos[0], pos[1], sub[-1][0], sub[-1][1],
                                                available_movement_cost=move_ft)
                except Exception:
                    path = None
                if path and dest_ok(tuple(sub[-1]), path):
                    break
                path = None
                sub = sub[:-1]
            if not path:
                continue
            end = tuple(path[-1])
            left = max(0, int((len(full) - len(path)) * feet))
            out.append((end, path, f"advance toward {name}: {end} (~{left} ft still to go)"))
        return out

    # -- final enrichment ------------------------------------------------------ #
    def _enrich(self, battle, entity, action) -> Any:
        """Last-ditch defaults if a required param is still unset."""
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.spell_action import SpellAction
        from natural20.actions.help_action import HelpAction
        from natural20.actions.shove_action import ShoveAction
        from natural20.actions.grapple_action import GrappleAction
        try:
            if isinstance(action, AttackAction) and getattr(action, 'target', None) is None \
                    and getattr(action, 'target_square', None) is None:
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
                    # Distracting an enemy (an ally's next attack has
                    # advantage) beats aiding an ally's ability check.
                    targets = []
                    for kinds in (['enemies'], ['allies']):
                        try:
                            targets = [t for t in battle.valid_targets_for(entity, action, target_types=kinds)
                                       if t is not entity]
                        except Exception:
                            targets = []
                        if targets:
                            break
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


def _is_point_target(target) -> bool:
    """True for a map coordinate (``[x, y]``) rather than creature target(s)."""
    return (isinstance(target, (list, tuple)) and len(target) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in target))


def _spell_key(action) -> Tuple[Optional[str], int]:
    return (_spell_name(action), int(getattr(action, 'at_level', 0) or 0))


def _round_robin_by_spell(leaves: List[Tuple[str, Any, str]]) -> List[Tuple[str, Any, str]]:
    """Interleave spell leaves so each distinct spell appears before any repeats.

    Keeps the incoming order within each spell and orders spells by their
    first (best-ranked) leaf, so one spell with many targets or squares
    (Mage Hand, Misty Step) cannot fill the per-type cap on its own.
    """
    groups: Dict[Any, List[Tuple[str, Any, str]]] = {}
    for leaf in leaves:
        groups.setdefault(_spell_key(leaf[1]), []).append(leaf)
    ordered: List[Tuple[str, Any, str]] = []
    queues = list(groups.values())
    depth = 0
    while queues:
        queues = [q for q in queues if len(q) > depth]
        ordered.extend(q[depth] for q in queues)
        depth += 1
    return ordered


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


def _blind_attack_text(action, weapon_name) -> str:
    """Leaf text for an attack on a square holding an unseen creature."""
    x, y = action.target_square
    heard = float(getattr(action, 'blind_confidence', 0) or 0) >= 1.0
    where = 'heard there now' if heard else 'last known position, it may have moved'
    return (f"attack unseen creature at square [{x}, {y}] ({where}) with {weapon_name}"
            f" (disadvantage; misses if nothing is there)")


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
            if t is None and getattr(action, 'target_square', None) is not None:
                return _blind_attack_text(action, w)
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
        if getattr(action, 'action_type', None) == 'action_surge':
            return 'action surge (free: gain one more action this turn, e.g. attack again)'
        if getattr(action, 'action_type', None) == 'drop_grapple':
            t = getattr(action, 'target', None)
            return f"release grapple on {_target_name(t, names) if t is not None else 'all held creatures'} (free, restores full speed)"
        if getattr(action, 'action_type', None) in ('summon_creatures', 'dismiss_summons'):
            return action.describe()
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


def jev_select_callout(provider, battle, entity, options: List[dict], action=None) -> Optional[dict]:
    """Let JEV pick the strategic callout for this turn from *options*.

    *options* come from ``combat_strategy.strategy_options`` (first entry is
    "stay silent"). The state is the same text the action decision sees, plus
    the action just chosen. Returns the chosen option, or ``None`` when the
    model is unavailable or answers out of range (caller falls back).
    """
    if provider is None or not getattr(provider, 'is_available', False) or not options:
        return None
    planner = JevActionPlanner(provider, max_decisions=1)
    try:
        planner._battle = battle
        planner._entity = entity
        planner._map = battle.map_for(entity)
        planner._session = getattr(battle, 'session', None)
        planner._names = planner._display_names(battle, entity)
        lines = planner._render_state(battle, entity).splitlines()
    except Exception as e:
        logger.debug("[JevPlan] callout state failed: %s", e)
        return None
    lines = [ln for ln in lines if not ln.startswith('Task:')]
    if action is not None:
        try:
            lines.append(f"this turn you: {_leaf_desc(action, planner._names)}")
        except Exception:
            pass
    lines.append(
        "Task: choose what, if anything, to call out to your allies this turn "
        "(a brief shout enemies may overhear). Pick the callout that most helps "
        "your side win, or stay silent if nothing is worth saying."
    )
    descs = [o.get('desc') or str(o.get('kind')) for o in options]
    idx = planner._decide("\n".join(lines), descs)
    if idx is None:
        return None
    logger.debug("[JevPlan] %s callout: %r", getattr(entity, 'name', '?'), descs[idx])
    return options[idx]
