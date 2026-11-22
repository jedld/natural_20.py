"""Fixed-encounter battles: load a scenario, run a seeded trial, aggregate a report.

This drives ``Battle`` directly. It does not start combat-recap, kill-reaction,
or callout-phrasing hooks, and it does not go through the Gymnasium env.
"""

from __future__ import annotations

import hashlib
import random
import statistics
import subprocess
import time
from pathlib import Path

import yaml

from natural20.battle import Battle
from natural20.controller import Controller
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.sim.seed import seed_process
from natural20.utils.monster_traits import (
    legendary_resistance_max,
    legendary_resistance_remaining,
)

MAX_ACTION_CYCLES = 12
_COUNTER_ATTRS = ('second_wind_count', 'action_surge_count')


class EncounterError(ValueError):
    """A scenario file cannot be loaded or run."""


class RandomController(Controller):
    """Uniform choice over the legal action list GenericController builds."""

    POLICY_ID = "random"

    def __init__(self, session):
        super().__init__(session)
        self._menu = GenericController(session)

    def move_for(self, entity, battle):
        if getattr(entity, 'incapacitated', lambda: False)():
            return None
        actions = [a for a in self._menu._compute_available_moves(entity, battle) if a]
        if not actions:
            return None
        return random.choice(actions)

    def select_action(self, battle, entity, available_actions=None):
        if not available_actions:
            return None
        return random.choice(list(available_actions))


def session_root_for(scenario_path, root=None) -> Path:
    """Directory that holds ``game.yml`` for this scenario."""
    if root is not None:
        candidate = Path(root).resolve()
        if not (candidate / 'game.yml').is_file():
            raise EncounterError(f"no game.yml under session root {candidate}")
        return candidate
    path = Path(scenario_path).resolve()
    for parent in [path.parent, *path.parents]:
        if (parent / 'game.yml').is_file():
            return parent
    raise EncounterError(f"no game.yml above {path}")


def load_scenario(scenario_path, root=None) -> dict:
    path = Path(scenario_path).resolve()
    if not path.is_file():
        raise EncounterError(f"scenario not found: {path}")
    with path.open('r', encoding='utf-8') as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise EncounterError(f"scenario {path} must be a mapping")
    scenario = dict(raw)
    scenario['_path'] = path
    scenario['_root'] = session_root_for(path, root=root)
    scenario.setdefault('id', path.stem)
    scenario.setdefault('max_rounds', 30)
    _validate(scenario)
    return scenario


def run_trial(scenario_path, seed, *, explain=False, max_rounds=None, root=None) -> dict:
    """Run one battle. ``seed`` fixes dice and uuids for this process."""
    seed = int(seed)
    seed_process(seed)
    scenario = load_scenario(scenario_path, root=root)
    started = time.perf_counter()
    session, battle, sides = _build_battle(scenario, explain=explain)
    before = {entity: _resource_snapshot(entity) for entity in sides['party'] + sides['monsters']}
    battle.start()
    outcome, trace = _run_battle(
        battle,
        max_rounds=int(max_rounds if max_rounds is not None else scenario['max_rounds']),
    )
    winner, end = _winner(battle, outcome)
    combatants = []
    for side_name, members in sides.items():
        for entity in members:
            after = _resource_snapshot(entity)
            prior = before[entity]
            combatants.append({
                'name': entity.name,
                'side': side_name,
                'hp': int(entity.hp() or 0),
                'max_hp': int(entity.max_hp() or 0),
                'dead': bool(entity.dead()),
                'slots_spent': _spent_maps(prior['slots'], after['slots']),
                'pools_spent': _spent_maps(prior['pools'], after['pools']),
            })
    policies = {
        side: (scenario['sides'][side].get('policy')
               or _policy_id(scenario['sides'][side]['controller']))
        for side in ('party', 'monsters')
    }
    return {
        'scenario': scenario['id'],
        'scenario_sha256': _file_sha256(scenario['_path']),
        'ruleset': getattr(session.ruleset, 'name', None),
        'policies': policies,
        'seed': seed,
        'git_revision': git_revision(scenario['_root']),
        'winner': winner,
        'end': end,
        'rounds': int(getattr(battle, 'round', 0) or 0),
        'wall_time_s': round(time.perf_counter() - started, 3),
        'combatants': combatants,
        'trace': trace,
    }


def run_trials(scenario_path, trials, seed, *, jobs=1, explain=False, max_rounds=None, root=None) -> dict:
    """Run seeds ``seed .. seed+trials-1`` and return an aggregate report."""
    trials = int(trials)
    if trials < 1:
        raise EncounterError("trials must be >= 1")
    jobs = max(1, int(jobs))
    seeds = [int(seed) + i for i in range(trials)]
    started = time.perf_counter()
    if jobs == 1:
        results = [
            run_trial(scenario_path, trial_seed, explain=explain, max_rounds=max_rounds, root=root)
            for trial_seed in seeds
        ]
    else:
        import multiprocessing
        payload = [
            (str(scenario_path), trial_seed, explain, max_rounds, None if root is None else str(root))
            for trial_seed in seeds
        ]
        context = multiprocessing.get_context('spawn')
        with context.Pool(jobs) as pool:
            results = pool.map(_trial_worker, payload)
    elapsed = time.perf_counter() - started
    return aggregate(results, elapsed)


def aggregate(results, elapsed_s) -> dict:
    """Win, wipe, round, survival, and resource totals across trials."""
    if not results:
        raise EncounterError("no trials to aggregate")
    n = len(results)
    first = results[0]
    party_wins = sum(1 for r in results if r['winner'] == 'party')
    monster_wins = sum(1 for r in results if r['winner'] == 'monsters')
    timeouts = sum(1 for r in results if r['winner'] == 'timeout')
    party_wipes = sum(1 for r in results if _side_wiped(r, 'party'))
    monster_wipes = sum(1 for r in results if _side_wiped(r, 'monsters'))
    rounds = [int(r['rounds']) for r in results]
    names = []
    for combatant in first['combatants']:
        names.append((combatant['name'], combatant['side']))
    combatant_rows = []
    for name, side in names:
        rows = [_combatant(r, name) for r in results]
        rows = [row for row in rows if row is not None]
        alive = sum(1 for row in rows if not row['dead'])
        hp_values = [0 if row['dead'] else int(row['hp']) for row in rows]
        dealt, taken = _damage_for(results, name)
        combatant_rows.append({
            'name': name,
            'side': side,
            'survival_rate': _rate(alive, n),
            'mean_hp': round(sum(hp_values) / n, 2),
            'mean_slots_spent': _mean_spent(rows, 'slots_spent', n),
            'mean_pools_spent': _mean_spent(rows, 'pools_spent', n),
            'mean_damage_dealt': round(dealt / n, 2),
            'mean_damage_taken': round(taken / n, 2),
        })
    return {
        'scenario': first['scenario'],
        'scenario_sha256': first['scenario_sha256'],
        'ruleset': first['ruleset'],
        'policies': first['policies'],
        'seed': first['seed'],
        'trials': n,
        'git_revision': first['git_revision'],
        'party_wins': party_wins,
        'monster_wins': monster_wins,
        'timeouts': timeouts,
        'party_wipes': party_wipes,
        'monster_wipes': monster_wipes,
        'party_win_rate': _rate(party_wins, n),
        'monster_win_rate': _rate(monster_wins, n),
        'timeout_rate': _rate(timeouts, n),
        'party_wipe_rate': _rate(party_wipes, n),
        'monster_wipe_rate': _rate(monster_wipes, n),
        'rounds': {
            'mean': round(sum(rounds) / n, 2),
            'median': round(float(statistics.median(rounds)), 2),
            'p90': round(_percentile(rounds, 0.9), 2),
        },
        'encounters_per_second': round(n / elapsed_s, 3) if elapsed_s > 0 else None,
        'wall_time_s': round(elapsed_s, 3),
        'combatants': combatant_rows,
        'games': results,
    }


def format_report(report) -> str:
    """Terminal table for one aggregate report."""
    lines = [
        f"{report['scenario']}  trials={report['trials']}  seed={report['seed']}  "
        f"ruleset={report['ruleset']}",
        f"  party wins {report['party_wins']}/{report['trials']} ({report['party_win_rate']:.0%})"
        f"  monsters {report['monster_wins']}/{report['trials']} ({report['monster_win_rate']:.0%})"
        f"  timeouts {report['timeouts']}/{report['trials']} ({report['timeout_rate']:.0%})",
        f"  party wipes {report['party_wipes']}/{report['trials']} ({report['party_wipe_rate']:.0%})"
        f"  monster wipes {report['monster_wipes']}/{report['trials']} ({report['monster_wipe_rate']:.0%})",
        f"  rounds mean {report['rounds']['mean']}  median {report['rounds']['median']}"
        f"  p90 {report['rounds']['p90']}"
        f"  {report['encounters_per_second']} encounters/s",
        f"  {'name':<16} {'side':<10} {'survive':>8} {'hp':>8} {'dealt':>8} {'taken':>8}",
    ]
    for row in report['combatants']:
        lines.append(
            f"  {row['name']:<16} {row['side']:<10} {row['survival_rate']:>8.0%}"
            f" {row['mean_hp']:>8.1f} {row['mean_damage_dealt']:>8.1f} {row['mean_damage_taken']:>8.1f}"
        )
        slots = row['mean_slots_spent']
        pools = row['mean_pools_spent']
        if slots or pools:
            lines.append(f"    slots {slots}  pools {pools}")
    return "\n".join(lines)


def git_revision(start: Path) -> str:
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=str(start),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip() or 'unknown'
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def _trial_worker(payload):
    path, seed, explain, max_rounds, root = payload
    return run_trial(path, seed, explain=explain, max_rounds=max_rounds, root=root)


def _validate(scenario: dict) -> None:
    sides = scenario.get('sides')
    if not isinstance(sides, dict) or 'party' not in sides or 'monsters' not in sides:
        raise EncounterError(f"{scenario.get('id')}: sides.party and sides.monsters are required")
    if not scenario.get('map'):
        raise EncounterError(f"{scenario.get('id')}: map is required")
    for side in ('party', 'monsters'):
        block = sides[side] or {}
        controller = block.get('controller', 'generic')
        if controller not in ('generic', 'random'):
            raise EncounterError(f"{scenario.get('id')}: unknown controller {controller!r}")
        members = block.get('members') or []
        if not members:
            raise EncounterError(f"{scenario.get('id')}: {side} has no members")
        for member in members:
            if 'template' not in member and 'npc' not in member:
                raise EncounterError(f"{scenario.get('id')}: member needs template or npc")
            count = int(member.get('count', 1))
            positions = member.get('positions') or []
            if len(positions) != count:
                raise EncounterError(
                    f"{scenario.get('id')}: {member.get('template') or member.get('npc')} "
                    f"has {len(positions)} positions for count {count}"
                )


def _build_battle(scenario, explain=False):
    root = scenario['_root']
    session = Session(root_path=str(root), event_manager=EventManager())
    map_key = str(scenario['map'])
    battle_map = (session.maps or {}).get(map_key)
    if battle_map is None:
        raise EncounterError(f"map {map_key!r} is not loaded from {root / 'game.yml'}")
    battle = Battle(session, battle_map)
    sides = {'party': [], 'monsters': []}
    for side in ('party', 'monsters'):
        block = scenario['sides'][side]
        for member in block['members']:
            count = int(member.get('count', 1))
            base = member.get('name') or member.get('template') or member.get('npc')
            for index, pos in enumerate(member['positions']):
                name = base if count == 1 else f"{base} {index + 1}"
                entity = _make_member(session, member, name)
                controller = _make_controller(session, block.get('controller', 'generic'), explain=explain)
                battle.add(entity, side, position=(int(pos[0]), int(pos[1])), controller=controller)
                sides[side].append(entity)
    return session, battle, sides


def _make_member(session, member, name):
    if member.get('template'):
        try:
            pc = PlayerCharacter.load(session, f"characters/{member['template']}")
        except FileNotFoundError as exc:
            raise EncounterError(f"unknown character template {member['template']}") from exc
        pc.name = name
        return pc
    npc_id = member['npc']
    try:
        return session.npc(npc_id, {'name': name})
    except FileNotFoundError as exc:
        raise EncounterError(f"unknown npc {npc_id}") from exc


def _make_controller(session, kind, explain=False):
    if kind == 'random':
        return RandomController(session)
    controller = GenericController(session)
    controller.explain = bool(explain)
    return controller


def _policy_id(kind: str) -> str:
    if kind == 'random':
        return RandomController.POLICY_ID
    return GenericController.POLICY_ID


def _run_battle(battle, max_rounds):
    """Turn loop shaped like ``Battle.while_active``.

    Dead combatants are skipped, and legendary creatures act at the end of
    someone else's turn. LLM narration hooks are not registered.
    """
    trace = []
    seen = 0
    order = battle.combat_order or []
    guard = max(8, (max_rounds + 2) * max(1, len(order)) * 4)
    steps = 0
    while steps < guard:
        steps += 1
        battle.skip_dead_turns(max_rounds)
        if battle.round > max_rounds:
            return 'timeout', trace
        battle.start_turn()
        current = battle.current_turn()
        if current is None:
            return 'timeout', trace
        ctrl = battle.controller_for(current)
        if ctrl:
            try:
                ctrl.begin_turn(current)
            except Exception:
                pass
        if current.conscious() and not current.incapacitated():
            current.reset_turn(battle)
            if current.dead():
                battle._end_of_turn_fired = (battle.round, battle.current_turn_index)
                result = battle.next_turn(max_rounds=max_rounds)
                if result == 'tpk':
                    return 'tpk', trace
                if result:
                    return 'timeout', trace
                continue
            _take_actions(battle, current, trace)
            seen = len(battle.battle_log)
        elif current.incapacitated() and not current.dead():
            pass
        try:
            current.resolve_trigger('end_of_turn')
        except Exception:
            pass
        battle.eval_legendary_action()
        _append_new_log(battle, trace, seen)
        seen = len(battle.battle_log)
        result = battle.next_turn(max_rounds=max_rounds)
        if result == 'tpk':
            return 'tpk', trace
        if result:
            return 'timeout', trace
    return 'timeout', trace


def _take_actions(battle, entity, trace):
    cycles = 0
    while cycles < MAX_ACTION_CYCLES:
        cycles += 1
        if entity.unconscious() or entity.dead() or entity.incapacitated():
            break
        try:
            action = battle.move_for(entity)
        except Exception:
            break
        if not action:
            break
        ctrl = battle.controller_for(entity)
        explain = None
        if ctrl is not None and getattr(ctrl, 'explain', False):
            explain = list(getattr(ctrl, 'last_explanation', None) or [])
        before = len(battle.battle_log)
        battle.action(action)
        battle.commit(action)
        for logged in battle.battle_log[before:]:
            row = _trace_row(battle.round, logged)
            if logged is action and explain:
                row['explain'] = explain
            trace.append(row)
        if entity.unconscious() or entity.dead():
            break


def _append_new_log(battle, trace, seen):
    for logged in battle.battle_log[seen:]:
        trace.append(_trace_row(battle.round, logged))


def _trace_row(round_n, action) -> dict:
    actor = getattr(getattr(action, 'source', None), 'name', None) or ''
    target = _target_label(getattr(action, 'target', None))
    if not target:
        path = getattr(action, 'move_path', None) or []
        if path:
            end = path[-1]
            target = f"{int(end[0])},{int(end[1])}"
    rolls = []
    for item in getattr(action, 'result', None) or []:
        if not isinstance(item, dict):
            continue
        kind = item.get('type')
        if kind not in ('hit', 'miss', 'damage', 'critical'):
            continue
        entry = {'type': kind}
        tname = _target_label(item.get('target'))
        if tname:
            entry['target'] = tname
        damage = _as_int(item.get('damage'))
        if damage is not None and kind in ('damage', 'hit', 'critical'):
            entry['damage'] = damage
        rolls.append(entry)
    return {
        'round': int(round_n or 0),
        'actor': actor,
        'action': getattr(action, 'action_type', '') or '',
        'target': target or '',
        'rolls': rolls,
    }


def _target_label(target) -> str:
    if target is None:
        return ''
    if hasattr(target, 'name'):
        return str(target.name)
    if isinstance(target, (list, tuple)):
        if len(target) == 2 and all(isinstance(v, (int, float)) for v in target):
            return f"{int(target[0])},{int(target[1])}"
        return ",".join(label for label in (_target_label(item) for item in target) if label)
    return ''


def _as_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if hasattr(value, 'result'):
        try:
            return int(value.result())
        except (TypeError, ValueError):
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _winner(battle, outcome):
    if outcome != 'tpk':
        return 'timeout', 'timeout'
    winners = battle.winning_groups()
    party_up = 'party' in winners
    monsters_up = 'monsters' in winners
    if party_up and not monsters_up:
        return 'party', 'wipe'
    if monsters_up and not party_up:
        return 'monsters', 'wipe'
    return 'none', 'wipe'


def _resource_snapshot(entity) -> dict:
    slots = {}
    raw_slots = getattr(entity, 'spell_slots', None) or {}
    for klass, table in raw_slots.items():
        if not isinstance(table, dict):
            continue
        for level, current in table.items():
            try:
                level_i = int(level)
            except (TypeError, ValueError):
                continue
            if level_i < 1:
                continue
            slots[str(level_i)] = slots.get(str(level_i), 0) + int(current or 0)
    pools = {}
    try:
        for name, pool in (entity.character_resource_pools() or {}).items():
            pools[str(name)] = int(pool.current)
    except Exception:
        pass
    for attr in _COUNTER_ATTRS:
        value = getattr(entity, attr, None)
        if value is not None:
            pools[attr] = int(value)
    if legendary_resistance_max(entity):
        pools['legendary_resistance'] = int(legendary_resistance_remaining(entity))
    return {'slots': slots, 'pools': pools}


def _spent_maps(before: dict, after: dict) -> dict:
    spent = {}
    for key, start in before.items():
        used = int(start) - int(after.get(key, start))
        if used > 0:
            spent[str(key)] = used
    return spent


def _side_wiped(result, side) -> bool:
    members = [row for row in result['combatants'] if row['side'] == side]
    return bool(members) and all(row['dead'] for row in members)


def _combatant(result, name):
    for row in result['combatants']:
        if row['name'] == name:
            return row
    return None


def _damage_for(results, name):
    dealt = 0
    taken = 0
    for result in results:
        for row in result.get('trace') or []:
            for roll in row.get('rolls') or []:
                damage = roll.get('damage')
                if not isinstance(damage, int):
                    continue
                if row.get('actor') == name:
                    dealt += damage
                if roll.get('target') == name:
                    taken += damage
    return dealt, taken


def _mean_spent(rows, key, n):
    totals = {}
    for row in rows:
        for name, amount in (row.get(key) or {}).items():
            totals[name] = totals.get(name, 0) + int(amount)
    return {name: round(amount / n, 2) for name, amount in sorted(totals.items())}


def _rate(count, n) -> float:
    return round(count / n, 4) if n else 0.0


def _percentile(values, p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()
