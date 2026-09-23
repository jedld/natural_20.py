#!/usr/bin/env python3
"""Headless battle simulation: JEV (TypeSafe System One) vs baseline AIs.

Drives a real ``Battle`` loop (start_turn -> begin_turn -> reset_turn ->
move_for/action/commit -> end_turn -> next_turn, mirroring the webapp
``ai_loop``) across configurable scenarios with randomized rosters:

Scenarios (``--scenario``, comma-separated list):
  pc_vs_npc   1 random PC vs 4 random light-CR NPCs  (default)
  duel        1 PC vs 1 NPC
  npc_vs_npc  3 random NPCs vs 3 random NPCs
  pc_vs_pc    2 random PCs vs 2 random PCs
  team_pvp    3 random PCs vs 3 random PCs

Each side runs its own controller arm (``--side-a-ai`` / ``--side-b-ai``):
  generic   GenericController heuristics (seeded random, deterministic)
  random    uniform random choice over legal actions
  jev       LlmMcpController + live JevProvider (TypeSafe System One API)
  llm       LlmMcpController + chat model at --llm-url (comparison arm)

Legacy flags still work: ``--opponent {generic,random,both}`` selects the
side-A arm and ``--npc-ai {jev,llm,generic}`` the side-B arm.

``--goblin-hp`` overrides goblin HP on either side (40 = Krizzit-fixture
buff, 7 = vanilla SRD). ``--log-dir`` writes one battle log per game.
Any provider failure falls back safely to the generic heuristic controller
(call failures are counted and reported).

Examples:
    # full scenario matrix, JEV (side B) vs generic (side A), 5 games each
    python scripts/jev_battle_sim.py \
        --scenario pc_vs_npc,duel,npc_vs_npc,pc_vs_pc,team_pvp \
        --side-a-ai generic --side-b-ai jev --repeat 5 \
        --max-rounds 10 --out sim_variety.json --log-dir logs/ --quiet

Environment (loaded from n20-webapp/webapp/.env):
    TYPESAFE_API_KEY   required for a jev arm (or TYPESAFE_BASE_URL /
                       TYPESAFE_MODEL / JEV_TIMEOUT)
    N20_SIM_LLM_URL    default --llm-url (OpenAI-compatible server)
    N20_SIM_LLM_MODEL  default --llm-model
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
from natural20.actions.move_action import MoveAction
from webapp.llm_handler import JevProvider, LlamaCppProvider

# LLM comparison arm: any OpenAI-compatible server. LlamaCppProvider
# appends /v1 itself, so the base URL must be the server root (a trailing
# /v1 is stripped below).
LLM_BASE_URL = os.environ.get('N20_SIM_LLM_URL', 'http://jedld-strix:8081')
LLM_MODEL = os.environ.get('N20_SIM_LLM_MODEL') or None


def normalize_llm_url(url):
    url = url.rstrip('/')
    if url.endswith('/v1'):
        url = url[:-3]
    return url


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


class CountingLlamaProvider(LlamaCppProvider):
    """LlamaCppProvider that counts chat calls, failures, and latency.

    The LLM comparison arm: LlmMcpController drives the entity via the usual
    chat prompt (integer-index response), in contrast to Jev's typed
    decide_action API.
    """

    def __init__(self, config):
        super().__init__(config)
        self.chat_calls = 0
        self.failures = 0
        self.latencies = []

    def send_message(self, messages):
        self.chat_calls += 1
        t0 = time.perf_counter()
        try:
            result = super().send_message(messages)
        except Exception as e:
            self.failures += 1
            self.latencies.append(time.perf_counter() - t0)
            logger_fail(f"llm send_message failed: {e}")
            return f"[LLM call failed: {e}]"
        self.latencies.append(time.perf_counter() - t0)
        if not result:
            self.failures += 1
        return result


def logger_fail(msg):
    import logging
    logging.getLogger('jev_battle_sim').warning(msg)


# --- randomized roster pools -------------------------------------------------
# PC fixtures with sane stats (the 67-HP level-1/2 rogue fixtures are
# copy-paste artifacts and are excluded).
PC_POOL = [
    'high_elf_fighter.yml', 'human_fighter.yml', 'elf_ranger.yml',
    'human_sorcerer.yml', 'human_warlock.yml', 'tabaxi_rogue.yml',
    'silvery_barbs_wizard.yml', 'tiefling_warlock.yml', 'tiefling_fighter.yml',
    'dwarf_cleric.yml', 'high_elf_mage.yml', 'human_bard.yml',
    'human_druid.yml', 'human_monk.yml', 'goliath_paladin.yml',
    'goliath_barbarian.yml', 'half_orc_barbarian.yml',
]

# Light-CR NPC pool (CR <= 0.5) so 1v4 and 3v3 matchups are roughly fair.
NPC_POOL_LIGHT = ['goblin', 'skeleton', 'wolf', 'giant_rat', 'hobgoblin', 'human_guard']

SCENARIOS = {
    'pc_vs_npc': {
        'a': ('pc', 1), 'b': ('npc', 4),
        'pos_a': [[0, 4]],
        'pos_b': [[8, 1], [9, 3], [8, 5], [9, 7]],
    },
    'duel': {
        'a': ('pc', 1), 'b': ('npc', 1),
        'pos_a': [[1, 4]], 'pos_b': [[8, 4]],
    },
    'npc_vs_npc': {
        'a': ('npc', 3), 'b': ('npc', 3),
        'pos_a': [[0, 1], [0, 4], [0, 7]],
        'pos_b': [[9, 1], [9, 4], [9, 7]],
    },
    'pc_vs_pc': {
        'a': ('pc', 2), 'b': ('pc', 2),
        'pos_a': [[0, 2], [0, 5]],
        'pos_b': [[9, 2], [9, 5]],
    },
    'team_pvp': {
        'a': ('pc', 3), 'b': ('pc', 3),
        'pos_a': [[0, 1], [0, 4], [0, 7]],
        'pos_b': [[9, 1], [9, 4], [9, 7]],
    },
}

ARM_CHOICES = ['generic', 'random', 'jev', 'llm']


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


def llm_move_options(battle, session, entity, limit_offensive=3, limit_defensive=2):
    """
    Full-speed, pre-pathed move destinations for the LLM comparison arm:
    squares adjacent to enemies (close the gap) plus squares that maximize
    distance from them (retreat). Mirrors the option set the JEV planner
    is shown, so both model arms face the same decision shape instead of
    the engine's 8 single-step moves.
    """
    from natural20.ai.path_compute import PathCompute

    out = []
    m = battle.map_for(entity)
    pos = m.position_of(entity)
    move_ft = entity.available_movement(battle)
    if pos is None or move_ft <= 0:
        return out
    pos = tuple(pos)
    pc = PathCompute(battle, m, entity)
    mx, my = m.size
    seen = set()

    def add(cand):
        if cand in seen or cand == pos:
            return
        try:
            path = pc.compute_path(pos[0], pos[1], cand[0], cand[1],
                                   available_movement_cost=move_ft)
        except Exception:
            return
        if not path or len(path) < 2:
            return
        end = tuple(path[-1])
        try:
            if not m.placeable(entity, *end, battle):
                return
            if m.entity_at(end[0], end[1]) is not None:
                return
        except Exception:
            return
        seen.add(cand)
        act = MoveAction(session, entity, 'move')
        act.move_path = list(path)
        out.append(act)

    enemies = []
    try:
        enemies = [e for e in battle.opponents_of(entity)
                   if battle.can_see(entity, e) and not e.dead()]
        enemies = sorted(enemies, key=lambda e: m.distance(entity, e))
    except Exception:
        pass

    # offensive: squares adjacent to the nearest enemies
    offensive_added = 0
    for e in enemies:
        if offensive_added >= limit_offensive:
            break
        epos = m.position_of(e)
        if epos is None:
            continue
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                cand = (epos[0] + dx, epos[1] + dy)
                if 0 <= cand[0] < mx and 0 <= cand[1] < my:
                    before = len(out)
                    add(cand)
                    if len(out) > before:
                        offensive_added += 1

    # defensive: farthest squares within reach
    if enemies:
        maxr = max(1, int(move_ft // (getattr(m, 'feet_per_grid', 5) or 5)))
        cands = []
        for dx in range(-maxr, maxr + 1):
            for dy in range(-maxr, maxr + 1):
                cand = (pos[0] + dx, pos[1] + dy)
                if 0 <= cand[0] < mx and 0 <= cand[1] < my and cand != pos:
                    cands.append(cand)

        def min_enemy_dist(c):
            try:
                ds = [m.distance(entity, e, entity_1_pos=c) for e in enemies]
                return min(ds) if ds else 0
            except Exception:
                return 0

        cands.sort(key=min_enemy_dist, reverse=True)
        added = 0
        for cand in cands:
            if added >= limit_defensive:
                break
            before = len(out)
            add(cand)
            if len(out) > before:
                added += 1
    return out


def llm_action_menu(battle, ctrl, entity):
    """
    Action menu for the LLM comparison arm: every attack/special action
    from the standard controller menu (auto-targeted, executable) plus a
    compact set of full-speed move destinations (see llm_move_options).
    """
    menu = [a for a in ctrl._compute_available_moves(entity, battle)
            if a is not None and not getattr(a, 'disabled', False)]
    specials = [a for a in menu if not isinstance(a, MoveAction)]
    try:
        moves = llm_move_options(battle, ctrl.session, entity)
    except Exception:
        moves = []
    return specials + moves


def take_actions_llm(battle, ctrl, entity, log):
    """
    LLM comparison arm: drive the chat model's decision path directly via
    ``controller.select_action(...)`` each cycle (the same flat-index
    ``send_message`` path the webapp uses for reactions), instead of the
    heuristic ``move_for``. Heuristic fallback applies on parse failure.
    """
    cycles = 0
    while cycles < 8:
        cycles += 1
        if entity.unconscious() or entity.dead() or entity.incapacitated():
            break
        try:
            menu = llm_action_menu(battle, ctrl, entity)
        except Exception as e:
            log(f"    ! action menu failed for {entity.name}: {e}")
            break
        if not menu:
            break
        try:
            action = ctrl.select_action(battle, entity, menu)
        except Exception as e:
            log(f"    ! select_action failed for {entity.name}: {e}")
            break
        if not action:
            break
        battle.action(action)
        battle.commit(action)
        describe_action(log, entity, action)
        if entity.unconscious() or entity.dead():
            break


def run_battle(battle, log, max_rounds, llm_entities=()):
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
            if current in llm_entities and ctrl is not None:
                take_actions_llm(battle, ctrl, current, log)
            else:
                take_actions(battle, current, log)
        elif current.incapacitated() and not current.dead():
            log(f"    - {current.name} is incapacitated, turn skipped")
        current.resolve_trigger('end_of_turn')
        result = battle.next_turn(max_rounds=max_rounds)
        if result == 'tpk':
            return 'tpk'
        if result:
            return 'max_rounds'


def pc_roster_info(pc, fixture):
    info = {'name': pc.name, 'kind': 'pc', 'fixture': fixture}
    try:
        cls = pc.class_and_level()
        if cls:
            info['class'] = cls[0][0]
            info['level'] = cls[0][1]
    except Exception:
        pass
    return info


def make_entity(session, kind, index, pool_pick, used_names, goblin_hp, team_tag=''):
    """Create one combatant from the roster pool and disambiguate its name."""
    if kind == 'pc':
        pc = PlayerCharacter.load(session, pool_pick)
        name = pc.name
        base = name
        n = 2
        while name in used_names:
            try:
                cls = pc.class_and_level()[0][0]
            except Exception:
                cls = 'pc'
            name = f"{base} ({cls}{n})"
            n += 1
        pc.name = name
        used_names.add(name)
        return pc
    npc_kind = pool_pick
    npc = session.npc(npc_kind)
    base = npc_kind[:1].upper() + npc_kind[1:]
    name = f"{base} {team_tag}{index + 1}".replace('  ', ' ')
    n = 2
    while name in used_names:
        name = f"{base} {team_tag}{index + 1}-{n}".replace('  ', ' ')
        n += 1
    npc.name = name
    used_names.add(name)
    if npc_kind == 'goblin' and goblin_hp:
        npc.properties['max_hp'] = goblin_hp
        npc.setup_attributes()
    return npc


def make_controller(session, arm, providers):
    if arm == 'generic':
        return GenericController(session)
    if arm == 'random':
        return RandomController(session)
    if arm in ('jev', 'llm'):
        return LlmMcpController(session, llm_provider=providers[arm])
    raise ValueError(f"unknown controller arm: {arm}")


def build_run(scenario, side_a_ai, side_b_ai, seed, map_name='jev_arena',
              goblin_hp=40, llm_url=LLM_BASE_URL, llm_model=LLM_MODEL):
    """Build one fresh battle for a scenario.

    Returns (session, map, battle, team_a, team_b, providers, roster_info)
    where providers maps arm name -> counting provider (jev/llm only) and
    roster_info is {'a': [roster entries], 'b': [...]}.
    """
    random.seed(seed)  # deterministic dice (and NPC random names)
    session = Session(root_path=os.path.join('tests', 'fixtures'), event_manager=EventManager())
    m = Map(session, map_name)
    battle = Battle(session, m)

    spec = SCENARIOS[scenario]
    roster_rng = random.Random(f"roster-{scenario}-{seed}")
    providers = {}
    if side_a_ai == 'jev' or side_b_ai == 'jev':
        provider = CountingJevProvider({})
        if not provider.initialize({}) or not provider.is_available:
            raise RuntimeError("JEV provider failed to initialize (TYPESAFE_API_KEY?)")
        providers['jev'] = provider
    if side_a_ai == 'llm' or side_b_ai == 'llm':
        url = normalize_llm_url(llm_url)
        cfg = {'base_url': url}
        if llm_model:
            cfg['model'] = llm_model
        provider = CountingLlamaProvider(cfg)
        if not provider.initialize({}) or not provider.current_model:
            raise RuntimeError(f"llama.cpp provider failed to initialize at {url}")
        providers['llm'] = provider

    def build_team(kind, count, positions, arm, group, token_base, tag):
        entities = []
        roster = []
        if kind == 'pc':
            picks = roster_rng.sample(PC_POOL, count)
        else:
            picks = roster_rng.sample(NPC_POOL_LIGHT, count)
        for i, pick in enumerate(picks):
            ent = make_entity(session, kind, i, pick, used_names, goblin_hp, team_tag=tag)
            battle.add(ent, group, position=positions[i],
                       token=token_base if kind == 'pc' else pick[:1].upper())
            battle.set_controller_for(ent, make_controller(session, arm, providers))
            entities.append(ent)
            if kind == 'pc':
                roster.append(pc_roster_info(ent, pick))
            else:
                roster.append({'name': ent.name, 'kind': 'npc', 'npc': pick})
        return entities, roster

    used_names = set()
    team_a, roster_a = build_team(spec['a'][0], spec['a'][1], spec['pos_a'], side_a_ai, 'a', 'G', 'A')
    team_b, roster_b = build_team(spec['b'][0], spec['b'][1], spec['pos_b'], side_b_ai, 'b', 'R', 'B')
    return session, m, battle, team_a, team_b, providers, {'a': roster_a, 'b': roster_b}


def play_game(scenario, side_a_ai, side_b_ai, seed, map_name='jev_arena',
              max_rounds=10, verbose=True, goblin_hp=40, log_dir=None,
              llm_url=LLM_BASE_URL, llm_model=LLM_MODEL):
    session, m, battle, team_a, team_b, providers, roster_info = build_run(
        scenario, side_a_ai, side_b_ai, seed, map_name=map_name,
        goblin_hp=goblin_hp, llm_url=llm_url, llm_model=llm_model)
    combatants = team_a + team_b
    spawn_pos = {id(c): m.entity_or_object_pos(c) for c in combatants}
    log_lines = []

    def log(msg):
        log_lines.append(str(msg))
        if verbose:
            print(msg, flush=True)

    header = (f"--- game seed={seed} scenario={scenario} "
              f"side_a={side_a_ai} side_b={side_b_ai} ---")
    print(header if verbose else "", flush=True)
    if verbose:
        for c in combatants:
            grp = battle.entity_group_for(c) or '?'
            print(f"  [{grp}] {c.name:<16} hp={hp_line(c)} pos={m.entity_or_object_pos(c)}")
        battle.start()
        print("initiative: " + " > ".join(e.name for e in battle.combat_order))
    else:
        battle.start()

    t0 = time.time()
    llm_entities = tuple(e for e in combatants
                         if e in _arm_entities(providers, side_a_ai, side_b_ai, team_a, team_b, 'llm'))
    outcome = run_battle(battle, log, max_rounds=max_rounds, llm_entities=llm_entities)
    elapsed = time.time() - t0

    a_alive = any(not c.dead() and not c.unconscious() for c in team_a)
    b_alive = any(not c.dead() and not c.unconscious() for c in team_b)
    if a_alive and not b_alive:
        winner = 'a'
    elif b_alive and not a_alive:
        winner = 'b'
    else:
        winner = 'draw'

    if verbose:
        print(f"outcome: {outcome} rounds={battle.round} time={elapsed:.1f}s winner={winner}")
        for c in combatants:
            state = 'dead' if c.dead() else ('unconscious' if c.unconscious() else 'alive')
            print(f"  {c.name:<16} {hp_line(c):>10}  {state}  pos={m.entity_or_object_pos(c)}")
        for arm, prov in providers.items():
            print(f"  provider[{arm}]: {provider_calls(prov)} api calls, {prov.failures} failures")

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{scenario}_{seed}_{side_a_ai}_vs_{side_b_ai}.log")
        with open(log_path, 'w') as f:
            f.write(header + "\n")
            for side, team, roster in (('a', team_a, roster_info['a']),
                                       ('b', team_b, roster_info['b'])):
                for ent, info in zip(team, roster):
                    label = (f"{info.get('class', info.get('npc', '?'))}"
                             f"{' ' + str(info['level']) if info.get('level') else ''}")
                    f.write(f"  side {side}: {info['name']} <{label}> "
                            f"spawn={spawn_pos[id(ent)]}\n")
            f.write("initiative: " + " > ".join(e.name for e in battle.combat_order) + "\n")
            f.write("\n".join(log_lines) + "\n")
            f.write(f"outcome: {outcome} rounds={battle.round} winner={winner} "
                    f"time={elapsed:.1f}s\n")
            f.write("final state:\n")
            for c in combatants:
                state = 'dead' if c.dead() else ('unconscious' if c.unconscious() else 'alive')
                f.write(f"  {c.name:<16} {hp_line(c):>10}  {state}  pos={m.entity_or_object_pos(c)}\n")

    def ent_info(c):
        info = {'name': c.name, 'team': 'a' if c in team_a else 'b',
                'hp': c.hp(), 'max_hp': c.max_hp(), 'dead': c.dead()}
        if isinstance(c, PlayerCharacter):
            try:
                cls = c.class_and_level()
                if cls:
                    info['class'] = cls[0][0]
                    info['level'] = cls[0][1]
            except Exception:
                pass
        return info

    return {
        'seed': seed,
        'scenario': scenario,
        'side_a_ai': side_a_ai,
        'side_b_ai': side_b_ai,
        'goblin_hp': goblin_hp,
        'roster': roster_info,
        'provider_a': provider_stats(providers.get(side_a_ai)),
        'provider_b': provider_stats(providers.get(side_b_ai)),
        'outcome': outcome,
        'rounds': battle.round,
        'winner': winner,
        'wall_time_s': round(elapsed, 1),
        'entities': [ent_info(c) for c in combatants],
    }


def _arm_entities(providers, side_a_ai, side_b_ai, team_a, team_b, arm_name):
    """Entities (if any) that run on the named provider arm."""
    ents = []
    if side_a_ai == arm_name:
        ents.extend(team_a)
    if side_b_ai == arm_name:
        ents.extend(team_b)
    return ents


def provider_calls(provider):
    if isinstance(provider, CountingJevProvider):
        return provider.decide_calls + provider.bool_calls
    if isinstance(provider, CountingLlamaProvider):
        return provider.chat_calls
    return 0


def provider_calls_of(result, side):
    p = result.get(f'provider_{side}')
    if not p:
        return 0
    if p.get('kind') == 'jev':
        return p.get('decide_action_calls', 0) + p.get('decide_bool_calls', 0)
    return p.get('chat_calls', 0)


def provider_stats(provider):
    if provider is None:
        return None
    base = {
        'failures': provider.failures,
        'avg_latency_s': round(sum(provider.latencies) / len(provider.latencies), 3) if provider.latencies else 0,
    }
    if isinstance(provider, CountingJevProvider):
        base.update({
            'kind': 'jev',
            'decide_action_calls': provider.decide_calls,
            'decide_bool_calls': provider.bool_calls,
        })
    elif isinstance(provider, CountingLlamaProvider):
        base.update({'kind': 'llm', 'chat_calls': provider.chat_calls, 'model': provider.current_model})
    return base


def probe_provider(arm, llm_url, llm_model):
    """Validate a model arm is reachable before the run starts."""
    if arm == 'jev':
        provider = CountingJevProvider({})
        if not provider.initialize({}) or not provider.is_available:
            print("ERROR: JEV provider not available. Set TYPESAFE_API_KEY "
                  "(see n20-webapp/webapp/env.example).", file=sys.stderr)
            sys.exit(2)
    elif arm == 'llm':
        probe = CountingLlamaProvider({'base_url': normalize_llm_url(llm_url),
                                       **({'model': llm_model} if llm_model else {})})
        if not probe.initialize({}) or not probe.current_model:
            print(f"ERROR: llm provider not reachable at {llm_url}", file=sys.stderr)
            sys.exit(2)
        print(f"llm provider: {probe.current_model} @ {probe.base_url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--map', default='jev_arena')
    parser.add_argument('--scenario', default='pc_vs_npc',
                        help="comma-separated list from: " + ",".join(SCENARIOS))
    parser.add_argument('--side-a-ai', choices=ARM_CHOICES, default=None,
                        help='side A controller arm (default: --opponent or generic)')
    parser.add_argument('--side-b-ai', choices=ARM_CHOICES, default=None,
                        help='side B controller arm (default: --npc-ai or jev)')
    parser.add_argument('--opponent', choices=['generic', 'random', 'both'], default=None,
                        help='legacy: side A controller (both = run both arms)')
    parser.add_argument('--npc-ai', choices=['jev', 'llm', 'generic'], default=None,
                        help='legacy: side B controller (default jev)')
    parser.add_argument('--goblin-hp', type=int, default=40,
                        help='goblin HP override (40=Krizzit-fixture buff, 7=vanilla SRD)')
    parser.add_argument('--llm-url', default=LLM_BASE_URL,
                        help='OpenAI-compatible server for the llm arm')
    parser.add_argument('--llm-model', default=LLM_MODEL,
                        help='model id for the llm arm (default: first /v1/models)')
    parser.add_argument('--repeat', type=int, default=1, help='games per scenario/arm pair')
    parser.add_argument('--max-rounds', type=int, default=10)
    parser.add_argument('--seed', type=int, default=20260921)
    parser.add_argument('--out', default=None, help='write JSON results to this path')
    parser.add_argument('--log-dir', default=None, help='write one battle log per game here')
    parser.add_argument('--quiet', action='store_true', help='no per-turn log')
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenario.split(',') if s.strip()]
    for s in scenarios:
        if s not in SCENARIOS:
            print(f"ERROR: unknown scenario {s!r}; choose from {list(SCENARIOS)}", file=sys.stderr)
            sys.exit(2)

    side_a_arms = [args.side_a_ai] if args.side_a_ai else \
        (['generic', 'random'] if args.opponent == 'both' else [args.opponent or 'generic'])
    side_b_arms = [args.side_b_ai] if args.side_b_ai else [args.npc_ai or 'jev']

    for arm in sorted(set(side_a_arms) | set(side_b_arms)):
        probe_provider(arm, args.llm_url, args.llm_model)

    all_results = []
    total = len(scenarios) * len(side_a_arms) * len(side_b_arms) * args.repeat
    done = 0
    for si, scenario in enumerate(scenarios):
        for ai, side_a in enumerate(side_a_arms):
            for bi, side_b in enumerate(side_b_arms):
                for i in range(args.repeat):
                    seed = args.seed + si * 100000 + ai * 10000 + bi * 1000 + i
                    done += 1
                    result = play_game(scenario, side_a, side_b, seed, map_name=args.map,
                                       max_rounds=args.max_rounds,
                                       verbose=not args.quiet,
                                       goblin_hp=args.goblin_hp,
                                       log_dir=args.log_dir,
                                       llm_url=args.llm_url, llm_model=args.llm_model)
                    all_results.append(result)
                    print(f"  [{done}/{total}] seed={seed} {scenario} "
                          f"a={side_a} b={side_b} winner={result['winner']} "
                          f"rounds={result['rounds']} time={result['wall_time_s']}s",
                          flush=True)

    # --- win-rate summary ---
    print("=" * 72)
    print(f"WIN-RATE SUMMARY (goblin_hp={args.goblin_hp})")
    for si, scenario in enumerate(scenarios):
        for ai, side_a in enumerate(side_a_arms):
            for bi, side_b in enumerate(side_b_arms):
                games = [r for r in all_results
                         if r['scenario'] == scenario
                         and r['side_a_ai'] == side_a
                         and r['side_b_ai'] == side_b]
                if not games:
                    continue
                n = len(games)
                a_wins = sum(1 for r in games if r['winner'] == 'a')
                b_wins = sum(1 for r in games if r['winner'] == 'b')
                draws = sum(1 for r in games if r['winner'] == 'draw')
                avg_rounds = sum(r['rounds'] for r in games) / n
                avg_time = sum(r['wall_time_s'] for r in games) / n
                tail = []
                for side, arm in (('a', side_a), ('b', side_b)):
                    calls = sum(provider_calls_of(r, side) for r in games)
                    fails = sum((r.get(f'provider_{side}') or {}).get('failures', 0) for r in games)
                    tail.append(f"{arm} calls {calls} ({fails} fail)" if calls else f"{arm} no-api")
                print(f"  {scenario:<10} a={side_a:<8} b={side_b:<8} "
                      f"a wins {a_wins}/{n} ({a_wins / n:.0%}), "
                      f"b wins {b_wins}/{n} ({b_wins / n:.0%}), "
                      f"draws {draws}/{n} | "
                      f"avg rounds {avg_rounds:.1f}, avg {avg_time:.0f}s/game | "
                      f"{', '.join(tail)}")

    if args.out:
        with open(args.out, 'w') as f:
            json.dump({'args': vars(args), 'games': all_results}, f, indent=2)
        print(f"results written to {args.out}")


if __name__ == '__main__':
    main()
