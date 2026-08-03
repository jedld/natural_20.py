#!/usr/bin/env python3
"""Audit and sync ``upcast`` metadata in spells.yml files.

Usage:
  python scripts/sync_spell_upcast_metadata.py --check
  python scripts/sync_spell_upcast_metadata.py --write
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from natural20.utils.action_bar import spell_scales_with_slot  # noqa: E402

DEFAULT_SPELL_FILES = (
    ROOT / 'templates' / 'items' / 'spells.yml',
    ROOT / 'tests' / 'fixtures' / 'items' / 'spells.yml',
)


def detect_upcast(spell_name: str, spell_meta: dict) -> bool:
    """True when the spell benefits from casting in a higher slot."""
    if int(spell_meta.get('level', 0) or 0) <= 0:
        return False
    return spell_scales_with_slot(spell_meta, spell_name)


def audit_spell_file(path: Path) -> dict[str, bool]:
    spells = yaml.safe_load(path.read_text()) or {}
    return {
        name: detect_upcast(name, meta)
        for name, meta in spells.items()
        if isinstance(meta, dict)
    }


def _spell_block_bounds(lines: list[str], spell_name: str) -> tuple[int, int] | None:
    start = None
    for idx, line in enumerate(lines):
        if re.match(rf'^{re.escape(spell_name)}:\s*$', line):
            start = idx
            break
    if start is None:
        return None

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if re.match(r'^[A-Za-z_][\w]*:\s*$', lines[idx]):
            end = idx
            break
    return start, end


def patch_spell_file(path: Path, desired: dict[str, bool], *, dry_run: bool) -> list[str]:
    lines = path.read_text().splitlines(keepends=True)
    changes: list[str] = []

    for spell_name, should_upcast in sorted(desired.items()):
        bounds = _spell_block_bounds(lines, spell_name)
        if bounds is None:
            continue
        start, end = bounds
        block = lines[start:end]

        has_upcast = any(re.match(r'^\s*upcast:\s*', row) for row in block)
        has_higher_level = any(re.match(r'^\s*higher_level:\s*true', row) for row in block)

        new_block: list[str] = []
        replaced = False
        for row in block:
            if re.match(r'^\s*upcast:\s*', row):
                new_value = 'true' if should_upcast else 'false'
                current = 'true' if 'true' in row else 'false'
                if current != new_value:
                    changes.append(f'{path.name}:{spell_name} upcast {current} -> {new_value}')
                new_block.append(re.sub(r'upcast:\s*\w+', f'upcast: {new_value}', row))
                replaced = True
                continue
            if should_upcast and re.match(r'^\s*higher_level:\s*true', row):
                changes.append(f'{path.name}:{spell_name} removed legacy higher_level')
                continue
            new_block.append(row)

        if not replaced and should_upcast:
            inserted = False
            patched: list[str] = []
            for row in new_block:
                patched.append(row)
                if not inserted and re.match(r'^\s*level:\s*\d+', row):
                    indent = re.match(r'^(\s*)', row).group(1)
                    patched.append(f'{indent}upcast: true\n')
                    inserted = True
            if not inserted:
                header, *rest = new_block
                indent = '  '
                if rest:
                    m = re.match(r'^(\s*)', rest[0])
                    if m:
                        indent = m.group(1) or indent
                patched = [header, f'{indent}upcast: true\n', *rest]
            new_block = patched
            changes.append(f'{path.name}:{spell_name} added upcast: true')

        lines[start:end] = new_block

    if changes and not dry_run:
        path.write_text(''.join(lines))
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Apply metadata updates')
    parser.add_argument('--check', action='store_true', help='Exit 1 if updates are needed')
    parser.add_argument('paths', nargs='*', type=Path, default=list(DEFAULT_SPELL_FILES))
    args = parser.parse_args()

    dry_run = not args.write
    all_changes: list[str] = []

    for path in args.paths:
        if not path.exists():
            print(f'skip missing {path}')
            continue
        desired = audit_spell_file(path)
        scaling = sorted(name for name, flag in desired.items() if flag)
        print(f'{path}: {len(scaling)} upcast spells')
        changes = patch_spell_file(path, desired, dry_run=dry_run)
        all_changes.extend(changes)

    if all_changes:
        print('\n'.join(all_changes))
    else:
        print('All spell upcast metadata is up to date.')

    if args.check and all_changes:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
