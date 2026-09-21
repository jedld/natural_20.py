#!/usr/bin/env python3
"""Headless battle simulation: JEV (TypeSafe System One) NPCs vs baseline AIs.

Drives a real ``Battle`` loop (start_turn -> begin_turn -> reset_turn ->
move_for/action/commit -> end_turn -> next_turn, mirroring the webapp
``ai_loop``) with:

* Group ``a`` (party): a level 7 fighter run by a baseline controller:
    - ``generic`` (default): ``GenericController`` heuristics with a seeded
      ``random`` module (deterministic).
    - ``random``: uniform random choice over legal actions (random policy).
* Group ``b`` (NPCs): goblins + an ogre, each run by ``LlmMcpController``
  with a live ``JevProvider`` — the recursive action-tree planner
  (action type -> weapon/spell -> target) decides every action via the
  TypeSafe System One API.

Any JEV failure falls back safely to the generic heuristic controller
(provider call failures are counted and reported).

Run ``--repeat N`` games against each opponent to estimate win rates:

    python scripts/jev_battle_sim.py --opponent both --repeat 3 \
        --max-rounds 10 --out sim_result.json

Environment (loaded from n20-webapp/webapp/.env):
    TYPESAFE_API_KEY   required (or TYPESAFE_BASE_URL / TYPESAFE_MODEL / JEV_TIMEOUT)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'n20-webapp'))

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, 'n20-webapp', 'webapp', '.env'))

from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.controller import Controller
from natural20.player_character import PlayerCharacter
from natural20.generic_controller import GenericController
from natural20.llm_controller import LlmMcpController
from webapp.llm_handler import JevProvider


class RandomController(Controller):
    """Random policy: uniform choice over the legal action list."""

    def select_action(self, battle, entity, available_actions=None):
        if not available_actions:
            return None
        return random.choice(available_actions)


class CountingJevProvider(JevProvider):
    """JevProvider that counts API calls, failures, and latency."""

    def __init__(self, config):
        super().__init__(config)
        self.decide_calls = 0
        self.bool_calls = 0
        self.failures = 0
        self.latencies = []

    def decide_action(self, state, options):
        self.decide_calls += 1
        t0 = time.perf_counter()
        try:
            result = super().decide_action(state, options)
        except Exception:
            result = None
        self.latencies.append(time.perf_counter() - t0)
        if result is None:
            self.failures += 1
        return result

    def decide_bool(self, state, instructions):
        self.bool_calls += 1
        t0 = time.perf_counter()
        try:
            result = super().decide_bool(state, instructions)
        except Exception:
            result = None
        self.latencies.append(time.perf_counter() - t0)
        if result is None:
            self.failures += 1
        return result


NPC_DEFS = [
    ('Krizzit', 'goblin', 40, [9, 0]),
    ('Snikkit', 'goblin', 40, [9, 2]),
    ('Graznak', 'goblin', 40, [9, 7]),
    ('Uglug', 'ogre', None, [8, 4]),
]
FIGHTER_POS = [0, 4]


def hp_line(entity):
    return f"{entity.hp()}/{entity.max_hp()}"


def describe_action(log, actor, action):
    atype = action.action_type
    target = getattr(action, 'target', None)
    tname = target.name if target is not None and hasattr(target, 'name') else ''
    pos = ''
    if atype in ('move', 'reposition'):
        path = getattr(action, 'move_path', None)
        if path:
            pos = f" -> {path[-1]}"
    extra = ''
    for item in (getattr(action, 'result', None) or []):
        itype = item.get('type') if isinstance(item, dict) else None
        if itype in ('hit', 'critical', 'damage'):
            extra += f" | {itype} {item.get('damage', 0)} dmg"
        elif itype == 'miss':
            extra += ' | miss'
        elif itype == 'message':
            msg = item.get('message', '')
            if msg:
                extra += f" | {msg[:60]}"
    log(f"    {actor.name}: {atype} {tname}{pos}{extra}".rstrip())


def take_actions(battle, entity, log):
    """Run the entity's turn: repeat move_for -> action -> commit until it
    has no (more) actions, mirroring the webapp ``ai_loop`` (bounded)."""
    cycles = 0
    while cycles < 8:
        cycles += 1
        if entity.unconscious() or entity.dead() or entity.incapacitated():
            break
        try:
            action = battle.move_for(entity)
        except Exception as e:
            log(f"    ! move_for failed for {entity.name}: {e}")
            break
        if not action:
            break
        battle.action(action)
        battle.commit(action)
        describe_action(log, entity, action)
        if entity.unconscious() or entity.dead():
            break


def run_battle(battle, log, max_rounds):
    while True:
        battle.start_turn()
        current = battle.current_turn()
        ctrl = battle.controller_for(current)
        if ctrl:
            try:
                ctrl.begin_turn(current)
            except Exception as e:
                log(f"    ! begin_turn error for {current.name}: {e}")
        if current.conscious() and not current.incapacitated():
            current.reset_turn(battle)
            take_actions(battle, current, log)
        elif current.incapacitated() and not current.dead():
            log(f"    - {current.name} is incapacitated, turn skipped")
        current.resolve_trigger('end_of_turn')
        result = battle.next_turn(max_rounds=max_rounds)
        if result == 'tpk':
            return 'tpk'
        if result:
            return 'max_rounds'


def build_run(map_name, opponent, seed, npc_ai='jev'):
    """Build one fresh battle: returns (session, map, battle, fighter, npcs, provider).

    ``npc_ai`` is 'jev' (live JevProvider, default) or 'generic' (heuristic
    control group — no API calls, isolates JEV's marginal contribution).
    """
    random.seed(seed)  # deterministic dice (and NPC random names)
    session = Session(root_path=os.path.join('tests', 'fixtures'), event_manager=EventManager())
    m = Map(session, map_name)
    battle = Battle(session, m)

    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    battle.add(fighter, 'a', position=FIGHTER_POS, token='G')
    if opponent == 'random':
        battle.set_controller_for(fighter, RandomController(session))
    else:
        battle.set_controller_for(fighter, GenericController(session))

    provider = None
    if npc_ai == 'jev':
        provider = CountingJevProvider({})
        if not provider.initialize({}) or not provider.is_available:
            raise RuntimeError("JEV provider failed to initialize (TYPESAFE_API_KEY?)")
    npcs = []
    for name, kind, hp, pos in NPC_DEFS:
        npc = session.npc(kind)
        npc.name = name
        if hp is not None:
            npc.properties['max_hp'] = hp
            npc.setup_attributes()
        battle.add(npc, 'b', position=pos, token={'goblin': 'g', 'ogre': 'O'}.get(kind, kind[0].upper()))
        if npc_ai == 'jev':
            battle.set_controller_for(npc, LlmMcpController(session, llm_provider=provider))
        else:
            battle.set_controller_for(npc, GenericController(session))
        npcs.append(npc)
    return session, m, battle, fighter, npcs, provider


def play_game(map_name, opponent, seed, max_rounds, verbose, npc_ai='jev'):
    session, m, battle, fighter, npcs, provider = build_run(map_name, opponent, seed, npc_ai=npc_ai)
    combatants = [fighter] + npcs

    def log(msg):
        if verbose:
            print(msg, flush=True)

    print(f"--- game seed={seed} opponent={opponent} ---" if verbose else "", flush=True)
    if verbose:
        for c in combatants:
            print(f"  {c.name:<10} hp={hp_line(c)} pos={m.entity_or_object_pos(c)}")
        battle.start()
        print("initiative: " + " > ".join(e.name for e in battle.combat_order))
    else:
        battle.start()

    t0 = time.time()
    outcome = run_battle(battle, log, max_rounds=max_rounds)
    elapsed = time.time() - t0

    party_alive = not fighter.dead() and not fighter.unconscious()
    npc_alive = any(not c.dead() and not c.unconscious() for c in npcs)
    if party_alive and not npc_alive:
        winner = 'party'
    elif npc_alive and not party_alive:
        winner = 'npcs'
    else:
        winner = 'draw'

    if verbose:
        print(f"outcome: {outcome} rounds={battle.round} time={elapsed:.1f}s winner={winner}")
        for c in combatants:
            state = 'dead' if c.dead() else ('unconscious' if c.unconscious() else 'alive')
            print(f"  {c.name:<10} {hp_line(c):>10}  {state}  pos={m.entity_or_object_pos(c)}")
        if provider is not None:
            print(f"  jev: {provider.decide_calls} decide calls, {provider.failures} failures")

    jev_stats = {
        'decide_action_calls': provider.decide_calls,
        'decide_bool_calls': provider.bool_calls,
        'failures': provider.failures,
        'avg_latency_s': round(sum(provider.latencies) / len(provider.latencies), 3) if provider.latencies else 0,
    } if provider is not None else None
    return {
        'seed': seed,
        'opponent': opponent,
        'npc_ai': npc_ai,
        'outcome': outcome,
        'rounds': battle.round,
        'winner': winner,
        'wall_time_s': round(elapsed, 1),
        'fighter_hp': [fighter.hp(), fighter.max_hp()],
        'npcs': [
            {'name': c.name, 'hp': c.hp(), 'max_hp': c.max_hp(), 'dead': c.dead()}
            for c in npcs
        ],
        'jev': jev_stats,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', default='jev_arena')
    parser.add_argument('--opponent', choices=['generic', 'random', 'both'], default='generic',
                        help='party (baseline) controller')
    parser.add_argument('--npc-ai', choices=['jev', 'generic'], default='jev',
                        help='NPC squad controller: jev (live TypeSafe) or generic '
                             '(heuristic control group, no API calls)')
    parser.add_argument('--repeat', type=int, default=1, help='games per opponent (win-rate estimation)')
    parser.add_argument('--max-rounds', type=int, default=10)
    parser.add_argument('--seed', type=int, default=20260921)
    parser.add_argument('--out', default=None, help='write JSON results to this path')
    parser.add_argument('--quiet', action='store_true', help='no per-turn log')
    args = parser.parse_args()

    if args.npc_ai == 'jev':
        provider_probe = CountingJevProvider({})
        if not provider_probe.initialize({}) or not provider_probe.is_available:
            print("ERROR: JEV provider not available. Set TYPESAFE_API_KEY "
                  "(see n20-webapp/webapp/env.example).", file=sys.stderr)
            sys.exit(2)

    opponents = ['generic', 'random'] if args.opponent == 'both' else [args.opponent]
    all_results = []
    for oi, opponent in enumerate(opponents):
        for i in range(args.repeat):
            seed = args.seed + oi * 1000 + i
            result = play_game(args.map, opponent, seed, args.max_rounds,
                               verbose=not args.quiet, npc_ai=args.npc_ai)
            all_results.append(result)

    # --- win-rate summary ---
    print("=" * 64)
    print(f"WIN-RATE SUMMARY (npcs={args.npc_ai.upper()} vs party=baseline)")
    for opponent in opponents:
        games = [r for r in all_results if r['opponent'] == opponent]
        if not games:
            continue
        wins = sum(1 for r in games if r['winner'] == 'npcs')
        losses = sum(1 for r in games if r['winner'] == 'party')
        draws = sum(1 for r in games if r['winner'] == 'draw')
        n = len(games)
        avg_rounds = sum(r['rounds'] for r in games) / n
        avg_time = sum(r['wall_time_s'] for r in games) / n
        jev_games = [r for r in games if r['jev'] is not None]
        if jev_games:
            calls = sum(r['jev']['decide_action_calls'] + r['jev']['decide_bool_calls'] for r in jev_games)
            fails = sum(r['jev']['failures'] for r in jev_games)
            tail = f"jev calls {calls} ({fails} failures)"
        else:
            tail = "no jev (heuristic control)"
        print(f"  vs {opponent:<8} npc wins {wins}/{n} ({wins / n:.0%}), "
              f"losses {losses}/{n}, draws {draws}/{n} | "
              f"avg rounds {avg_rounds:.1f}, avg {avg_time:.0f}s/game, "
              f"{tail}")

    if args.out:
        with open(args.out, 'w') as f:
            json.dump({'args': vars(args), 'games': all_results}, f, indent=2)
        print(f"results written to {args.out}")


if __name__ == '__main__':
    main()
