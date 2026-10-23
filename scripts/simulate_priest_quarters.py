#!/usr/bin/env python3
"""Headless full-battle simulation of the dragonlance `priest_quarters` map.

Loads the campaign session (which auto-loads every map, including the
priest_quarters map with its 4 PCs and 9 enemy NPCs already placed), gives
every combatant a GenericController (the built-in heuristic 5e AI), and
drives the engine's canonical Battle loop (Battle.while_active:
skip_dead_turns -> start_turn -> begin_turn -> reset_turn -> actions ->
end_of_turn -> next_turn, mirroring the webapp turn loop) until one side is
wiped out or the round cap is hit.

The full combat log (initiative, per-turn banners, DM turn status lines,
attack rolls, saves, damage, deaths, movement) is written to a file and
echoed to stdout.

Usage:
    python scripts/simulate_priest_quarters.py [--seed 20] [--max-rounds 60]
        [--out logs/priest_quarters_combat.log] [--quiet] [--ai generic|jev|llm]

AI arms:
    generic (default)  GenericController heuristics, fully offline.
    jev                LlmMcpController + live JevProvider (TypeSafe System
                       One "JEV" decision model) for every combatant. Reads
                       TYPESAFE_API_KEY / TYPESAFE_BASE_URL / TYPESAFE_MODEL
                       (plus JEV_TIMEOUT) from n20-webapp/webapp/.env and the
                       environment. Each action is a live API round-trip
                       (typically a few seconds per turn), and any JEV
                       failure falls back safely to the generic heuristic.
    llm                LlmMcpController + live OpenAI-compatible chat provider
                       (default: local llama.cpp Qwen endpoint). Reads
                       SIM_LLM_BASE_URL / SIM_LLM_MODEL / SIM_LLM_API_KEY,
                       or use --llm-base-url/--llm-model/--llm-api-key.

Determinism:
    With --ai generic the same --seed reproduces the identical battle: the
    global ``random`` module (all engine dice) is seeded, and uuid4 is pinned
    to a seeded stand-in so the per-process entity/action/tile uids the
    engine mints at load time can't perturb set iteration order or AI
    tie-breaks. The only non-reproducible line is the wall-clock "Started"
    header. With --ai jev the battle is NOT reproducible: decisions come
    from a live remote model (dice are still seeded).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# n20-webapp on the path before importing natural20.llm_controller: that
# module binds webapp.llm_handler.JevProvider at import time, and the JEV
# decision path is gated on that binding.
sys.path.insert(0, str(ROOT / 'n20-webapp'))

from natural20.action import AsyncReactionHandler, BardicInspirationPrompt
from natural20.battle import Battle
from natural20.event_manager import EventManager, FileOutputLogger
from natural20.exceptions import GameLoopControl
from natural20.generic_controller import GenericController
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.llm_controller import LlmMcpController
from natural20.utils.escape_plan import has_escaped

CAMPAIGN_ROOT = ROOT / 'user_levels' / 'dragonlance'
MAP_KEY = 'priest_quarters'
DEFAULT_OUT = ROOT / 'logs' / 'priest_quarters_combat.log'

# Safety cap: a turn should never need more than a handful of actions.
MAX_ACTION_CYCLES = 20


def pin_uuid4(seed):
    """Make uuid4 deterministic for the process.

    The engine mints uuid4s at load time for entities without a YAML
    entity_uid, actions, and map tiles. Random per-process uids change set
    iteration order (and thus tie-breaks in AI decisions), which breaks run
    reproducibility even with a seeded ``random``. Uids are opaque labels, so
    deterministic stand-ins are safe.
    """
    import uuid
    rng = random.Random(f'n20-sim-uuid-{seed}')

    def _uuid4():
        return uuid.UUID(int=rng.getrandbits(128), version=4)

    uuid.uuid4 = _uuid4


def setup_jev_provider(log, request_logger=None):
    """Build a live JEV (TypeSafe System One) decision provider.

    Loads n20-webapp/webapp/.env for the TYPESAFE_* / JEV_TIMEOUT variables
    and returns a counting JevProvider, or None if it cannot be initialized
    (missing key, SDK, or endpoint). Every decide_* call is timed and counted
    so the summary can report JEV round-trips and fallbacks. An optional
    ``request_logger`` callback receives one JSON-serializable record per JEV
    request/response in a format suitable for finetuning a similar model.
    """
    try:
        import dotenv
    except ImportError:
        dotenv = None
    if dotenv is not None:
        dotenv.load_dotenv(ROOT / 'n20-webapp' / 'webapp' / '.env')
    try:
        from webapp.llm_handler import JevProvider
    except Exception as e:
        log(f"ERROR: cannot import webapp.llm_handler.JevProvider: {e}")
        return None

    class CountingJevProvider(JevProvider):
        def __init__(self):
            super().__init__({}, request_logger=request_logger)
            self.decide_calls = 0
            self.bool_calls = 0
            self.failures = 0
            self.latencies = []

        def _record(self, count, result):
            if result is None:
                count['failures'] += 1
            count['latencies'].append(time.perf_counter() - count['t0'])
            count['calls'] += 1

        def decide_action(self, state, options):
            c = {'t0': time.perf_counter(), 'calls': 0, 'failures': 0, 'latencies': []}
            try:
                result = super().decide_action(state, options)
            except Exception:
                result = None
            self._record(c, result)
            self.decide_calls += c['calls']
            self.failures += c['failures']
            self.latencies.extend(c['latencies'])
            return result

        def decide_bool(self, state, instructions):
            c = {'t0': time.perf_counter(), 'calls': 0, 'failures': 0, 'latencies': []}
            try:
                result = super().decide_bool(state, instructions)
            except Exception:
                result = None
            self._record(c, result)
            self.bool_calls += c['calls']
            self.failures += c['failures']
            self.latencies.extend(c['latencies'])
            return result

    provider = CountingJevProvider()
    if not provider.initialize({}) or not provider.is_available:
        log("ERROR: JEV provider failed to initialize "
            "(set TYPESAFE_API_KEY in n20-webapp/webapp/.env; install typesafe_sdk).")
        return None
    log(f"JEV provider ready: {provider.base_url} model={provider.current_model} "
        f"timeout={provider.request_timeout}s")
    return provider


def setup_llm_provider(log, base_url, model, api_key, timeout, max_tokens):
    try:
        from webapp.llm_handler import LlamaCppProvider
    except Exception as e:
        log(f"ERROR: cannot import webapp.llm_handler.LlamaCppProvider: {e}")
        return None

    class CountingLlmProvider(LlamaCppProvider):
        def __init__(self, opts):
            super().__init__(opts)
            self.decide_calls = 0
            self.bool_calls = 0
            self.failures = 0
            self.latencies = []

        def send_message(self, messages):
            t0 = time.perf_counter()
            try:
                result = super().send_message(messages)
            except Exception:
                result = None
            latency = time.perf_counter() - t0
            self.decide_calls += 1
            self.latencies.append(latency)
            if result is None or str(result).startswith(('Error communicating', 'Unexpected error')):
                self.failures += 1
            return result

    opts = {
        'base_url': base_url,
        'model': model,
        'api_key': api_key,
        'timeout': timeout,
        'max_tokens': max_tokens,
    }
    provider = CountingLlmProvider(opts)
    if not provider.initialize(opts):
        log("ERROR: LLM provider failed to initialize "
            f"(base_url={base_url}, model={model}).")
        return None
    log(f"LLM provider ready: {provider.base_url} model={provider.current_model} "
        f"timeout={provider.request_timeout}s max_tokens={provider.max_tokens}")
    return provider


class TeeOutputLogger(FileOutputLogger):
    """Write each line to the log file and optionally echo it to stdout."""

    def __init__(self, file_path, echo=True):
        super().__init__(file_path)
        self.echo = echo

    def log(self, event_msg, event=None, visibility=None):
        super().log(event_msg, event=event, visibility=visibility)
        if self.echo:
            print(event_msg)


def setup_logging(log_path: Path, echo: bool) -> EventManager:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Truncate any previous run so the file holds exactly this simulation.
    log_path.write_text('')
    event_manager = EventManager(output_logger=TeeOutputLogger(str(log_path), echo=echo))
    event_manager.standard_cli()

    def top_of_the_round(event):
        # battle.round is 0 during the first lap and increments on wrap, so
        # the human-readable round number is always battle.round + 1.
        event_manager.output_logger.log(f"\n----- ROUND {event['round'] + 1} -----")

    def end_of_combat(event):
        event_manager.output_logger.log("\n===== END OF COMBAT =====")

    def turn_skipped(event):
        statuses = ', '.join(event.get('statuses') or []) or 'incapacitated'
        event_manager.output_logger.log(
            f"    - {event_manager.decorate_name(event['target'])} is incapacitated "
            f"({statuses}); turn skipped.")

    event_manager.register_event_listener(['top_of_the_round'], top_of_the_round)
    event_manager.register_event_listener(['end_of_combat'], end_of_combat)
    event_manager.register_event_listener(['turn_skipped'], turn_skipped)
    return event_manager


def resolve_game_loop_control(battle, entity, action, prompt):
    """Auto-resolve a GameLoopControl raised mid-action.

    GenericController never raises these (its reactions resolve
    synchronously), but stay defensive in case a controller swap does.
    """
    log = battle.session.event_manager.output_logger.log
    if isinstance(prompt, BardicInspirationPrompt):
        from natural20.effects.bardic_inspiration_effect import would_bardic_inspiration_help
        use = would_bardic_inspiration_help(
            prompt.context.get('base_total'),
            prompt.context.get('threshold'),
            prompt.context.get('comparator'),
            prompt.context.get('die'),
        )
        log(f"    - {entity.name} {'uses' if use else 'holds'} Bardic Inspiration.")
        prompt.send(bool(use))
        return
    if isinstance(prompt, AsyncReactionHandler):
        picked = None
        for item in prompt.resolve():
            if not item:
                continue
            valid_actions = item[-1] if isinstance(item, (list, tuple)) else item
            if isinstance(valid_actions, (list, tuple)) and valid_actions:
                picked = valid_actions[0]
                break
        log(f"    - {entity.name} auto-resolved {prompt.reaction_type} "
            f"({'taken' if picked else 'skipped'}).")
        prompt.send(picked)
        return
    raise prompt  # Unknown control flow: surface it.


def take_turn(battle, entity):
    """Run one combatant's full turn of actions (mirrors the webapp ai_loop).

    Returns False so Battle.while_active proceeds to end-of-turn processing.
    """
    log = battle.session.event_manager.output_logger.log
    cycles = 0
    while True:
        cycles += 1
        if entity.dead() or entity.incapacitated() or battle.battle_ends():
            return False
        if cycles > MAX_ACTION_CYCLES:
            log(f"    - {entity.name}: action cycle cap ({MAX_ACTION_CYCLES}) reached; "
                f"ending turn.")
            return False
        action = battle.move_for(entity)
        if not action:
            return False
        try:
            battle.action(action)
            battle.commit(action)
        except GameLoopControl as prompt:
            resolve_game_loop_control(battle, entity, action, prompt)
            try:
                battle.action(action)
                battle.commit(action)
            except GameLoopControl as prompt2:
                log(f"    - {entity.name}: could not auto-resolve {prompt2!r}; "
                    f"ending turn.")
                return False


def write_summary(battle, result, args, log, provider=None, combatants=None, provider_name='AI'):
    log("")
    log("===== SIMULATION SUMMARY =====")
    if provider is not None:
        total = provider.decide_calls + provider.bool_calls
        avg = (sum(provider.latencies) / len(provider.latencies)
               if provider.latencies else 0.0)
        log(f"{provider_name} round-trips: {total} ({provider.decide_calls} action, "
            f"{provider.bool_calls} bool), {provider.failures} failures "
            f"(fell back to heuristics), avg {avg:.2f}s/call")
    escaped = [
        entity for entity in (combatants or [])
        if entity not in battle.combat_order and has_escaped(entity)
    ]
    if result == 'tpk':
        winners = sorted(battle.winning_groups() or [])
        log(f"Result: total party kill (or one side wiped) — "
            f"surviving group(s): {', '.join(winners) or 'none'}")
        if escaped:
            log(f"Escaped combatants: {', '.join(entity.name for entity in escaped)}")
    elif result:
        # A truthy (non-tpk) result means while_active stopped on the round
        # cap: both sides still had conscious combatants left (stalemate).
        log(f"Result: round cap reached (max {args.max_rounds}) while entering "
            f"round {battle.round + 1} — stalemate, both sides still standing.")
    else:
        log("Result: battle ended.")
    log(f"Rounds elapsed: {battle.round + 1}")
    log("")
    log(f"{'Entity':<28} {'Group':<6} {'HP':>10}  State")
    for entity in battle.combat_order:
        state = battle.entities[entity]
        group = state.get('group', '?')
        if entity.dead():
            hp_str, status = '0', 'dead'
        elif entity.unconscious():
            hp_str, status = '0', 'unconscious'
        else:
            hp_str = f"{entity.hp()}/{entity.max_hp()}"
            status = 'ok'
        log(f"{entity.name:<28} {str(group):<6} {hp_str:>10}  {status}")
    for entity in escaped:
        group = getattr(entity, 'group', None) or (entity.properties or {}).get('group', '?')
        hp_str = f"{entity.hp()}/{entity.max_hp()}"
        log(f"{entity.name:<28} {str(group):<6} {hp_str:>10}  escaped")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--seed', type=int,
                        default=int(os.environ.get('SIM_SEED', '20')),
                        help='Random seed for reproducible battles (default 20).')
    parser.add_argument('--max-rounds', type=int, default=60,
                        help='Stop after this many rounds (default 60).')
    parser.add_argument('--out', default=str(DEFAULT_OUT),
                        help='Combat log file path.')
    parser.add_argument('--ai', choices=['generic', 'jev', 'llm'], default='generic',
                        help='Combatant AI: GenericController heuristics (default), '
                             'live JEV (TypeSafe System One), or live OpenAI-compatible LLM.')
    parser.add_argument('--jev-log', default='',
                        help='JSONL path for raw JEV request/response records '
                             '(only used with --ai jev).')
    parser.add_argument('--llm-base-url', default=os.environ.get('SIM_LLM_BASE_URL', 'http://jedld-strix.local:8081'),
                        help='OpenAI-compatible llama.cpp base URL for --ai llm.')
    parser.add_argument('--llm-model', default=os.environ.get('SIM_LLM_MODEL', 'Qwen3.8-27B-UD-Q4_K_XL-nv-split'),
                        help='Model name for --ai llm.')
    parser.add_argument('--llm-api-key', default=os.environ.get('SIM_LLM_API_KEY', 'llama-cpp'),
                        help='API key for --ai llm.')
    parser.add_argument('--llm-timeout', type=int, default=int(os.environ.get('SIM_LLM_TIMEOUT', '120')),
                        help='Per-request timeout in seconds for --ai llm.')
    parser.add_argument('--llm-max-tokens', type=int, default=int(os.environ.get('SIM_LLM_MAX_TOKENS', '1000')),
                        help='Max completion tokens for --ai llm.')
    parser.add_argument('--quiet', action='store_true',
                        help='Do not echo the log to stdout.')
    args = parser.parse_args()

    random.seed(args.seed)
    pin_uuid4(args.seed)
    log_path = Path(args.out).resolve()
    event_manager = setup_logging(log_path, echo=not args.quiet)
    log = event_manager.output_logger.log

    log(f"=== Simulating {MAP_KEY} (seed={args.seed}, ai={args.ai}, "
        f"max_rounds={args.max_rounds}) ===")
    log(f"Started {time.strftime('%Y-%m-%d %H:%M:%S')}")

    jev_provider = None
    if args.ai == 'jev':
        request_logger = None
        if args.jev_log:
            jev_log_path = Path(args.jev_log).resolve()
            jev_log_path.parent.mkdir(parents=True, exist_ok=True)
            jev_log_path.write_text('')

            def request_logger(record):
                with open(jev_log_path, 'a', encoding='utf-8') as handle:
                    handle.write(json.dumps(record, default=str) + '\n')

        jev_provider = setup_jev_provider(log, request_logger=request_logger)
        if jev_provider is None:
            return 2
        if args.jev_log:
            log(f"JEV request log: {jev_log_path}")
    elif args.ai == 'llm':
        jev_provider = setup_llm_provider(
            log,
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
            timeout=args.llm_timeout,
            max_tokens=args.llm_max_tokens,
        )
        if jev_provider is None:
            return 2

    session = Session(root_path=str(CAMPAIGN_ROOT), event_manager=event_manager)
    if MAP_KEY not in session.maps:
        log(f"ERROR: map '{MAP_KEY}' not found in session.maps: {list(session.maps)}")
        return 2
    battle_map = session.maps[MAP_KEY]

    battle = Battle(session, battle_map)
    combatants = list(battle_map.entities)
    for entity in combatants:
        group = 'a' if isinstance(entity, PlayerCharacter) else 'b'
        if jev_provider is not None:
            # One controller per entity (session context is keyed by uid),
            # all sharing the same live JEV provider.
            controller = LlmMcpController(session, llm_provider=jev_provider)
        else:
            controller = GenericController(session)
        controller.register_handlers_on(entity)
        battle.add(entity, group, controller=controller)

    n_pcs = sum(1 for e in combatants if isinstance(e, PlayerCharacter))
    n_npcs = len(combatants) - n_pcs
    log(f"Combatants: {len(combatants)} ({n_pcs} PCs [group a] vs {n_npcs} NPCs [group b])")

    started = time.time()
    battle.start()
    # The engine only emits top_of_the_round when the round increments (on
    # wrap), so label the first lap ourselves.
    log("\n----- ROUND 1 -----")
    result = battle.while_active(
        max_rounds=args.max_rounds,
        callback=lambda entity: take_turn(battle, entity),
    )
    elapsed = time.time() - started

    # A battle that ends mid-loop (e.g. TPK on the last action) never reaches
    # next_turn, so end_of_combat is not fired by the engine.
    if battle.started and battle.battle_ends():
        battle.session.event_manager.received_event({'source': battle, 'event': 'end_of_combat'})
        battle.started = False
        if result is None:
            result = 'tpk'

    write_summary(
        battle,
        result,
        args,
        log,
        provider=jev_provider,
        combatants=combatants,
        provider_name='JEV' if args.ai == 'jev' else 'LLM',
    )
    print(f"\nDone in {elapsed:.1f}s — log: {log_path}")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
