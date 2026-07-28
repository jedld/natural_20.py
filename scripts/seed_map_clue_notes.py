#!/usr/bin/env python3
"""Add discoverable ``notes`` to map clue objects from existing ability_checks.

Interactive objects in campaign maps often define ``ability_checks`` for the
Interact action but omit ``notes``, which breaks Look/perception discovery and
the map note UI. This script copies surface text from ``conversation_buffer``
and gated detail from each ability check's ``success`` string.

Usage:
    python scripts/seed_map_clue_notes.py user_levels/outcasts_path/maps
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SKILL_DC_KEYS = {
    'investigation': 'investigation_dc',
    'perception': 'perception_dc',
    'insight': 'insight_dc',
    'religion': 'religion_dc',
    'arcana': 'arcana_dc',
    'medicine': 'medicine_dc',
    'nature': 'nature_dc',
}


def is_npc(props: dict) -> bool:
    return props.get('type') == 'npc' or bool(props.get('sub_type'))


def should_have_notes(props: dict) -> bool:
    if is_npc(props):
        return False
    if props.get('type') == 'teleporter' and not props.get('ability_checks'):
        return False
    return props.get('type') == 'interactive_object' or bool(props.get('ability_checks'))


def surface_note(props: dict) -> str | None:
    for buf in props.get('conversation_buffer') or []:
        if isinstance(buf, dict) and buf.get('message'):
            return str(buf['message']).strip()
    label = props.get('label')
    if label:
        return f'A marker labeled “{label}.”'
    return None


def build_notes(props: dict) -> list[dict]:
    notes: list[dict] = []
    surface = surface_note(props)
    if surface:
        notes.append({'note': surface})
    for skill, check in (props.get('ability_checks') or {}).items():
        if not isinstance(check, dict):
            continue
        success = check.get('success')
        if not success:
            continue
        dc = check.get('dc', 10)
        dc_key = SKILL_DC_KEYS.get(skill, 'investigation_dc')
        notes.append({'note': str(success).strip(), dc_key: dc})
    return notes


def merge_props(*dicts: dict) -> dict:
    out: dict = {}
    for item in dicts:
        if isinstance(item, dict):
            out.update(item)
    return out


def fix_container(props: dict, *, is_entity: bool = False) -> None:
    if not isinstance(props, dict):
        return
    if is_npc(props):
        props.pop('notes', None)
        overrides = props.get('overrides')
        if isinstance(overrides, dict):
            overrides.pop('notes', None)
        return
    if props.get('type') == 'teleporter' and not props.get('ability_checks'):
        props.pop('notes', None)
        return

    if is_entity and isinstance(props.get('overrides'), dict):
        overrides = props['overrides']
        merged = merge_props(props, overrides)
        if should_have_notes(merged):
            overrides['notes'] = build_notes(merged)
        else:
            overrides.pop('notes', None)
        props.pop('notes', None)
        return

    if should_have_notes(props):
        props['notes'] = build_notes(props)
    else:
        props.pop('notes', None)


def walk_map(data: dict) -> None:
    entities = data.get('map', {}).get('entities') or data.get('entities') or []
    for ent in entities:
        fix_container(ent, is_entity=True)
    legend = data.get('legend') or {}
    for entry in legend.values():
        fix_container(entry, is_entity=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('maps_dir', type=Path, help='Directory containing map YAML files')
    args = parser.parse_args(argv)
    maps_dir = args.maps_dir
    if not maps_dir.is_dir():
        print(f'Not a directory: {maps_dir}', file=sys.stderr)
        return 1

    for path in sorted(maps_dir.glob('*.yml')):
        if path.name == 'monsters.yml':
            continue
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            continue
        walk_map(data)
        path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding='utf-8',
        )
        print(f'updated {path.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
