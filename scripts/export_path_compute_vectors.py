#!/usr/bin/env python3
"""Export golden path vectors for webapp/static/path_compute.test.js."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from natural20.ai.path_compute import PathCompute
from natural20.ai.pathfinding_cost_map import (
    build_pathfinding_snapshot,
    compute_path_from_snapshot,
)
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


def _run_case(session, map_name: str, fighter, case: dict) -> dict:
    battle_map = Map(session, map_name)
    pc = PathCompute(None, battle_map, fighter)
    sx, sy = case['source']
    dx, dy = case['destination']
    kwargs = {}
    if case.get('door_navigation'):
        kwargs['door_navigation'] = True
    if case.get('available_movement_cost') is not None:
        kwargs['available_movement_cost'] = case['available_movement_cost']
    if case.get('accumulated_path'):
        kwargs['accumulated_path'] = [tuple(p) for p in case['accumulated_path']]

    expected = pc.compute_path(sx, sy, dx, dy, **kwargs)
    snapshot = build_pathfinding_snapshot(battle_map, fighter, None)
    from_snap = compute_path_from_snapshot(snapshot, sx, sy, dx, dy, **kwargs)
    if from_snap != expected:
        raise AssertionError(
            f"Snapshot path mismatch for {case.get('name')}: {from_snap!r} != {expected!r}"
        )
    return {
        'name': case['name'],
        'map': map_name,
        'source': [sx, sy],
        'destination': [dx, dy],
        'door_navigation': bool(case.get('door_navigation')),
        'available_movement_cost': case.get('available_movement_cost'),
        'accumulated_path': case.get('accumulated_path'),
        'expected_path': expected,
        'snapshot': snapshot,
    }


def main():
    session = Session(root_path=os.path.join(ROOT, 'tests', 'fixtures'))
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')

    cases = [
        {
            'name': 'basic_path',
            'source': [0, 0],
            'destination': [6, 6],
        },
        {
            'name': 'second_case',
            'source': [1, 3],
            'destination': [7, 4],
        },
        {
            'name': 'short_destination',
            'source': [0, 0],
            'destination': [3, 3],
        },
        {
            'name': 'unreachable',
            'source': [0, 1],
            'destination': [0, 4],
            'map': 'battle_sim_4',
            'npc': 'ogre',
        },
    ]

    out_cases = []
    for case in cases:
        map_name = case.get('map', 'path_finding_test')
        entity = fighter
        if case.get('npc'):
            entity = session.npc(case['npc'])
            battle_map = Map(session, map_name)
            battle_map.add(entity, case['source'][0], case['source'][1])
        out_cases.append(_run_case(session, map_name, entity, case))

    # difficult terrain map
    out_cases.append(_run_case(session, 'path_finding_test_2', fighter, {
        'name': 'difficult_terrain',
        'source': [2, 2],
        'destination': [3, 5],
    }))

    dests_case = {
        'name': 'multi_destinations',
        'source': [0, 0],
        'destinations': [[6, 6], [7, 4], [3, 3]],
    }
    battle_map = Map(session, 'path_finding_test')
    pc = PathCompute(None, battle_map, fighter)
    snapshot = build_pathfinding_snapshot(battle_map, fighter, None)
    multi = {}
    for dest in dests_case['destinations']:
        path = pc.compute_path(0, 0, dest[0], dest[1])
        snap_path = compute_path_from_snapshot(snapshot, 0, 0, dest[0], dest[1])
        if snap_path != path:
            raise AssertionError(f"multi dest {dest} mismatch")
        multi[f"{dest[0]},{dest[1]}"] = path
    out_cases.append({
        'name': 'multi_destinations',
        'snapshot': snapshot,
        'source': [0, 0],
        'paths': multi,
    })

    out_path = os.path.join(ROOT, 'tests', 'fixtures', 'path_compute_vectors.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'cases': out_cases}, f, indent=2)
    print(f"Wrote {len(out_cases)} cases to {out_path}")


if __name__ == '__main__':
    main()
