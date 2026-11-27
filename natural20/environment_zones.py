"""Out-of-combat persistent zone ticking (exploration / environment time)."""

from __future__ import annotations

from typing import Iterable, Optional


def _zones_for_map(battle_map):
    if battle_map is None:
        return []
    zones = getattr(battle_map, 'environment_zones', None)
    if zones is None:
        zones = []
        battle_map.environment_zones = zones
    return zones


def register_environment_zone(zone) -> None:
    battle_map = getattr(zone, 'map', None)
    if battle_map is None:
        return
    zones = _zones_for_map(battle_map)
    if zone not in zones:
        zones.append(zone)


def unregister_environment_zone(zone, *, dismiss: bool = False) -> None:
    battle_map = getattr(zone, 'map', None)
    if battle_map is None:
        return
    zones = _zones_for_map(battle_map)
    try:
        zones.remove(zone)
    except ValueError:
        pass
    if dismiss and not getattr(zone, '_dismissed', False):
        zone.dismiss()


def register_persistent_zone(zone, battle=None) -> None:
    """Register a zone for combat and/or exploration ticking."""
    if battle is not None:
        battle.register_zone(zone)
    else:
        register_environment_zone(zone)


def promote_environment_zones_to_battle(battle) -> None:
    """Move map-registered zones onto an active battle when combat starts."""
    if battle is None:
        return
    for battle_map in getattr(battle, 'maps', None) or []:
        for zone in list(_zones_for_map(battle_map)):
            battle.register_zone(zone)
            try:
                _zones_for_map(battle_map).remove(zone)
            except ValueError:
                pass
            zone.battle = battle


def demote_battle_zones_to_environment(battle) -> None:
    """Return active battle zones to map ticking when combat ends."""
    if battle is None:
        return
    for zone in list(getattr(battle, 'active_zones', []) or []):
        register_environment_zone(zone)
        zone.battle = None
    battle.active_zones.clear()


def trigger_environment_movement_step(battle_map, entity, from_pos, to_pos,
                                      *, event_manager=None) -> None:
    """Out-of-combat twin of ``Battle.trigger_movement_step``.

    ``Battle.trigger_movement_step`` only walks ``battle.active_zones``, so
    exploration zones (a Spike Growth cast while no battle is running, or a
    zone that never got promoted into the current battle) never fired their
    per-square hooks. ``MoveAction.apply`` calls this for the map's
    ``environment_zones`` after every path square, mirroring the battle
    dispatch: ``on_movement_step`` (Spike Growth damage, Web ...), and
    ``on_enter`` only when the entity was not already inside.
    """
    if battle_map is None or to_pos is None or not entity:
        return
    zones = _zones_for_map(battle_map)
    if not zones:
        return
    target = tuple(to_pos)
    for zone in list(zones):
        if getattr(zone, '_dismissed', False):
            continue
        if zone.expired():
            zone.dismiss()
            continue
        on_move = getattr(zone, 'on_movement_step', None)
        if callable(on_move):
            try:
                on_move(entity, from_pos, to_pos)
            except Exception as exc:  # pragma: no cover - defensive
                if event_manager is not None:
                    event_manager.received_event({
                        'source': zone, 'event': 'zone_error',
                        'phase': 'on_movement_step', 'error': str(exc),
                    })
        if not zone.contains(target):
            continue
        if from_pos is not None and zone.contains(tuple(from_pos)):
            continue
        try:
            zone.on_enter(entity)
        except Exception as exc:  # pragma: no cover - defensive
            if event_manager is not None:
                event_manager.received_event({
                    'source': zone, 'event': 'zone_error',
                    'phase': 'on_enter', 'error': str(exc),
                })


def tick_environment_zones(maps, *, event_manager=None) -> None:
    """Run ``on_turn_start`` zone hooks for every conscious entity once per tick."""
    if not maps:
        return

    map_list = maps.values() if isinstance(maps, dict) else maps
    for battle_map in map_list:
        zones = list(_zones_for_map(battle_map))
        if not zones:
            continue

        for zone in list(zones):
            if zone.expired():
                zone.dismiss()
                continue

        entities = getattr(battle_map, 'entities', None) or {}
        seen = set()
        for entity in list(entities.keys()):
            uid = getattr(entity, 'entity_uid', None) or id(entity)
            if uid in seen:
                continue
            seen.add(uid)
            try:
                if hasattr(entity, 'dead') and entity.dead():
                    continue
                if hasattr(entity, 'conscious') and not entity.conscious():
                    continue
            except Exception:
                continue

            for zone in list(_zones_for_map(battle_map)):
                if getattr(zone, '_dismissed', False) or zone.expired():
                    continue
                try:
                    zone.on_turn_start(entity)
                except Exception as exc:  # pragma: no cover - defensive
                    if event_manager is not None:
                        event_manager.received_event({
                            'source': zone,
                            'event': 'zone_error',
                            'phase': 'environment_tick',
                            'error': str(exc),
                        })
