#!/usr/bin/env python3
"""Diagnostic script to trace cross-map pathfinding for tavern navigation.

Usage:
    python scripts/diagnose_cross_map_path.py [campaign_dir]

Example:
    python scripts/diagnose_cross_map_path.py user_levels/wild_sheep_chase
"""

import json
import os
import sys

import yaml


def load_campaign(campaign_path: str):
    """Load a campaign session from the given directory."""
    from natural20.session import Session
    session = Session(campaign_path)
    return session


def diagnose_map_stack(session):
    """Check map stack configuration."""
    print("=== MAP STACK DIAGNOSTIC ===")
    print()

    # Check map_stacks registry
    registry = session.map_stacks
    print(f"Map stacks registered: {[s.id for s in registry.all_stacks()]}")

    for stack in registry.all_stacks():
        print(f"\n  Stack: {stack.id}")
        print(f"    Maps: {stack.maps_in_stack()}")
        for floor in stack.floors:
            print(f"    Floor: {floor.map_name} anchor={floor.anchor} elev={floor.elevation_ft} role={floor.role}")

    # Check amphail_tavern specifically
    tavern_stack = registry.stack_for_map('tavern_2nd_floor')
    if tavern_stack:
        print(f"\n  amphail_tavern stack found: {tavern_stack.id}")
        for floor in tavern_stack.floors:
            print(f"    - {floor.map_name}: anchor={floor.anchor}, elev={floor.elevation_ft}")

    # Check town_market stack
    market_stack = registry.stack_for_map('town_market')
    if market_stack:
        print(f"\n  town_market stack: {market_stack.id}")
    else:
        print(f"\n  town_market has NO stack (not part of any map_stack)")


def diagnose_transitions(session):
    """Check transitions_from for stairwell cells."""
    print("\n=== TRANSITIONS DIAGNOSTIC ===")
    print()

    town_market = session.maps.get('town_market')
    tavern_2nd = session.maps.get('tavern_2nd_floor')

    if not town_market or not tavern_2nd:
        print("ERROR: Missing town_market or tavern_2nd_floor")
        return

    # Check map_stack on each map
    print(f"town_market.map_stack: {town_market.map_stack}")
    print(f"tavern_2nd_floor.map_stack: {tavern_2nd.map_stack}")

    if town_market.map_stack is None:
        print("  --> CRITICAL: town_market has NO map_stack!")
        return

    stack = town_market.map_stack

    # Test transitions from stairwell cells (world coordinates)
    # The stairwell is at world cells (9,16) and (9,17) based on annotation bounds
    for wx, wy in [(9, 16), (9, 17)]:
        is_opening = stack.is_stack_opening(wx, wy)
        transitions = stack.transitions_from('town_market', wx, wy)
        print(f"\n  World ({wx},{wy}): is_stack_opening={is_opening}")
        print(f"    transitions_from('town_market', {wx}, {wy}) = {transitions}")

    # Check 2nd floor transitions (should go down)
    # The 2nd floor stairwell is at local (0,0), which maps to world (9,16)
    print(f"\n  2nd floor local (0,0):")
    is_opening = stack.is_stack_opening(9, 16)
    transitions = stack.transitions_from('tavern_2nd_floor', 0, 0)
    print(f"    is_stack_opening(9, 16) = {is_opening}")
    print(f"    transitions_from('tavern_2nd_floor', 0, 0) = {transitions}")


def diagnose_teleporters(session):
    """Check teleporter objects on each map."""
    print("\n=== TELEPORTER DIAGNOSTIC ===")
    print()

    town_market = session.maps.get('town_market')
    tavern_2nd = session.maps.get('tavern_2nd_floor')

    if not town_market or not tavern_2nd:
        print("ERROR: Missing maps")
        return

    # Check interactable_objects on each map
    print("town_market interactable_objects:")
    for obj, pos in town_market.interactable_objects.items():
        obj_type = getattr(obj, 'properties', {}).get('type', type(obj).__name__)
        target_map = getattr(obj, 'target_map', None)
        target_pos = getattr(obj, 'target_position', None)
        if target_map or obj_type == 'teleporter':
            print(f"  {obj.name} at {pos}: type={obj_type} target_map={target_map} target_pos={target_pos}")

    print("\ntavern_2nd_floor interactable_objects:")
    for obj, pos in tavern_2nd.interactable_objects.items():
        obj_type = getattr(obj, 'properties', {}).get('type', type(obj).__name__)
        target_map = getattr(obj, 'target_map', None)
        target_pos = getattr(obj, 'target_position', None)
        if target_map or obj_type == 'teleporter':
            print(f"  {obj.name} at {pos}: type={obj_type} target_map={target_map} target_pos={target_pos}")


def diagnose_linked_maps(session):
    """Check linked_maps dict on each map."""
    print("\n=== LINKED MAPS DIAGNOSTIC ===")
    print()

    for name, map_obj in session.maps.items():
        linked = list(map_obj.linked_maps.keys())
        print(f"{name}: linked_maps = {sorted(linked)}")


def annotate_stair_check(session):
    """Check the annotation for the stair shaft."""
    print("\n=== STAIR ANNOTATION DIAGNOSTIC ===")
    print()

    town_market = session.maps.get('town_market')
    tavern_2nd = session.maps.get('tavern_2nd_floor')

    if not town_market or not tavern_2nd:
        print("ERROR: Missing maps")
        return

    print("town_market map_annotations:")
    for ann in town_market.map_annotations():
        ann_id = ann.get('id', '')
        ann_kind = ann.get('kind', '')
        if 'stair' in ann_id.lower() or 'stair' in str(ann.get('label', '')).lower():
            print(f"  id={ann_id} kind={ann_kind} label={ann.get('label')}")
            print(f"    stack={ann.get('stack')}")
            print(f"    bounds={ann.get('bounds')}")
            print(f"    pos={ann.get('pos')}")

    print("\ntavern_2nd_floor map_annotations:")
    for ann in tavern_2nd.map_annotations():
        ann_id = ann.get('id', '')
        ann_kind = ann.get('kind', '')
        if 'stair' in ann_id.lower() or 'stair' in str(ann.get('label', '')).lower():
            print(f"  id={ann_id} kind={ann_kind} label={ann.get('label')}")
            print(f"    stack={ann.get('stack')}")
            print(f"    bounds={ann.get('bounds')}")
            print(f"    pos={ann.get('pos')}")


def annotate_suite_check(session):
    """Check the tavern_suite_room annotation."""
    print("\n=== SUITE ANNOTATION DIAGNOSTIC ===")
    print()

    tavern_2nd = session.maps.get('tavern_2nd_floor')

    if not tavern_2nd:
        print("ERROR: Missing tavern_2nd_floor")
        return

    for ann in tavern_2nd.map_annotations():
        ann_id = ann.get('id', '')
        if 'suite' in ann_id.lower():
            print(f"Found: id={ann_id}")
            print(f"  kind={ann.get('kind')}")
            print(f"  pos={ann.get('pos')}")
            print(f"  label={ann.get('label')}")
            print(f"  description={ann.get('description')}")


def test_pathcompute(session):
    """Run PathCompute to test cross-map pathfinding."""
    print("\n=== PATHCOMPUTE DIAGNOSTIC ===")
    print()

    from natural20.ai.path_compute import PathCompute
    from natural20.entity import Entity

    town_market = session.maps.get('town_market')
    tavern_2nd = session.maps.get('tavern_2nd_floor')

    if not town_market or not tavern_2nd:
        print("ERROR: Missing maps")
        return

    # Create a dummy entity for path computation
    dummy = Entity('test_entity', 'test_entity')
    dummy.size = (1, 1)
    dummy.half_width = 0.5
    dummy.half_height = 0.5

    # Test: can we path from town_market to tavern_2nd_floor suite?
    # NPC position: assume near the bar at (9, 19) on town_market
    # Suite position: (1, 3) on tavern_2nd_floor
    source_x, source_y = 9, 19
    dest_x, dest_y = 1, 3

    path_compute = PathCompute(None, town_market, dummy, ignore_opposing=True)

    print(f"Computing cross-map path:")
    print(f"  Source: {source_x},{source_y} on town_market")
    print(f"  Target: {dest_x},{dest_y} on tavern_2nd_floor")

    plan = path_compute.compute_cross_map_path(
        town_market, source_x, source_y,
        tavern_2nd, dest_x, dest_y,
        door_navigation=True,
    )

    if plan is None:
        print("  RESULT: None (no path found)")
    else:
        print(f"  RESULT: Found {len(plan)} segment(s)")
        for i, seg in enumerate(plan):
            print(f"    Segment {i}: map={seg['map'].name} path_len={len(seg['path'])} teleporter={seg.get('teleporter')} next_map={seg.get('next_map')}")
            if seg['path']:
                print(f"      path[:3]={seg['path'][:3]}...{'...' if len(seg['path']) > 3 else ''}")
                print(f"      path[-3:]={seg['path'][-3:]}")


def check_npc_known_places(session):
    """Check what landmarks Pip and Mara know about."""
    print("\n=== NPC KNOWN PLACES DIAGNOSTIC ===")
    print()

    # Find NPCs
    pip = session.entity_by_uid('pip_barmaid')
    mara = session.entity_by_uid('mara_bartender')

    for npc, name in [(pip, 'Pip'), (mara, 'Mara')]:
        if npc is None:
            print(f"  {name}: NOT FOUND")
            continue
        known = getattr(npc, 'properties', {}).get('known_places', [])
        print(f"  {name} ({npc.entity_uid}): known_places = {known}")
        try:
            pos = npc.position()
            print(f"    position = {pos}")
        except Exception:
            print(f"    position = unknown")


def main():
    campaign_path = sys.argv[1] if len(sys.argv) > 1 else 'user_levels/wild_sheep_chase'

    if not os.path.isdir(campaign_path):
        print(f"Error: {campaign_path} is not a directory")
        sys.exit(1)

    print(f"Loading campaign from: {campaign_path}")
    print()

    session = load_campaign(campaign_path)

    diagnose_map_stack(session)
    diagnose_transitions(session)
    diagnose_teleporters(session)
    diagnose_linked_maps(session)
    annotate_stair_check(session)
    annotate_suite_check(session)
    test_pathcompute(session)
    check_npc_known_places(session)

    print("\n=== DIAGNOSTIC COMPLETE ===")


if __name__ == '__main__':
    main()
