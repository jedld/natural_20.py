"""DM-only map pins stored in session state.

Notes are play-time reminders the dungeon master can drop on any square.
They persist with save/load via ``session.session_state['dm_notes']`` and
must never be mixed with YAML ``map_annotations`` (those are landmarks
for NPC navigation and LLM place context).

Visibility contract:
    * Only DM HTTP/MCP surfaces may read or write these records.
    * Do not inject into NPC prompts, RAG, ``npc.*`` tools, or player
      map HTML / ``/update`` payloads.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

_STATE_KEY = 'dm_notes'
_MAX_TEXT = 8000
_MAX_TITLE = 80


def _ensure_store(session) -> dict[str, list[dict[str, Any]]]:
    if session is None:
        return {}
    state = getattr(session, 'session_state', None)
    if not isinstance(state, dict):
        session.session_state = {}
        state = session.session_state
    raw = state.get(_STATE_KEY)
    if not isinstance(raw, dict):
        raw = {}
        state[_STATE_KEY] = raw
    return raw


def _game_time(session) -> int:
    try:
        return int(getattr(session, 'game_time', 0) or 0)
    except (TypeError, ValueError):
        return 0


def _clamp_text(value: Any, limit: int) -> str:
    return str(value or '').strip()[:limit]


def _title_from_text(text: str, title: Optional[str] = None) -> str:
    explicit = _clamp_text(title, _MAX_TITLE)
    if explicit:
        return explicit
    first_line = (text or '').splitlines()[0].strip() if text else ''
    if not first_line:
        return 'Note'
    if len(first_line) <= _MAX_TITLE:
        return first_line
    return first_line[: _MAX_TITLE - 1].rstrip() + '…'


def _normalize_map_name(map_name: Any) -> str:
    name = str(map_name or '').strip()
    if not name:
        raise ValueError('map_name is required')
    return name


def _normalize_xy(x: Any, y: Any) -> tuple[int, int]:
    try:
        xi = int(x)
        yi = int(y)
    except (TypeError, ValueError) as exc:
        raise ValueError('x and y must be integers') from exc
    if xi < 0 or yi < 0:
        raise ValueError('x and y must be >= 0')
    return xi, yi


def _copy_note(note: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': str(note.get('id') or ''),
        'map': str(note.get('map') or ''),
        'x': int(note.get('x', 0)),
        'y': int(note.get('y', 0)),
        'title': str(note.get('title') or 'Note'),
        'text': str(note.get('text') or ''),
        'created_at': int(note.get('created_at') or 0),
        'updated_at': int(note.get('updated_at') or 0),
    }


def list_notes(session, map_name: Optional[str] = None) -> list[dict[str, Any]]:
    store = _ensure_store(session)
    if map_name is None:
        items: list[dict[str, Any]] = []
        for name, rows in store.items():
            if not isinstance(rows, list):
                continue
            for note in rows:
                if isinstance(note, dict):
                    copied = _copy_note(note)
                    if not copied['map']:
                        copied['map'] = str(name)
                    items.append(copied)
        items.sort(key=lambda n: (n['map'], n['y'], n['x'], n['id']))
        return items
    key = _normalize_map_name(map_name)
    rows = store.get(key) or []
    if not isinstance(rows, list):
        return []
    items = []
    for note in rows:
        if isinstance(note, dict):
            copied = _copy_note(note)
            copied['map'] = key
            items.append(copied)
    items.sort(key=lambda n: (n['y'], n['x'], n['id']))
    return items


def find_note(session, note_id: str, map_name: Optional[str] = None) -> Optional[dict[str, Any]]:
    nid = str(note_id or '').strip()
    if not nid:
        return None
    if map_name:
        for note in list_notes(session, map_name):
            if note['id'] == nid:
                return note
        return None
    for note in list_notes(session, None):
        if note['id'] == nid:
            return note
    return None


def upsert_note(
    session,
    map_name: str,
    *,
    x: Any,
    y: Any,
    text: Any,
    title: Optional[str] = None,
    note_id: Optional[str] = None,
) -> dict[str, Any]:
    key = _normalize_map_name(map_name)
    xi, yi = _normalize_xy(x, y)
    body = _clamp_text(text, _MAX_TEXT)
    if not body:
        raise ValueError('text is required')
    store = _ensure_store(session)
    rows = store.get(key)
    if not isinstance(rows, list):
        rows = []
        store[key] = rows
    now = _game_time(session)
    existing_id = str(note_id or '').strip()
    if existing_id:
        for index, note in enumerate(rows):
            if not isinstance(note, dict):
                continue
            if str(note.get('id') or '') != existing_id:
                continue
            updated = _copy_note(note)
            updated.update({
                'map': key,
                'x': xi,
                'y': yi,
                'text': body,
                'title': _title_from_text(body, title if title is not None else note.get('title')),
                'updated_at': now,
            })
            if not updated.get('created_at'):
                updated['created_at'] = now
            rows[index] = updated
            return _copy_note(updated)
        raise ValueError(f'Note not found: {existing_id}')

    created = {
        'id': uuid.uuid4().hex,
        'map': key,
        'x': xi,
        'y': yi,
        'text': body,
        'title': _title_from_text(body, title),
        'created_at': now,
        'updated_at': now,
    }
    rows.append(created)
    return _copy_note(created)


def move_note(session, note_id: str, x: Any, y: Any, map_name: Optional[str] = None) -> dict[str, Any]:
    found = find_note(session, note_id, map_name)
    if found is None:
        raise ValueError(f'Note not found: {note_id}')
    xi, yi = _normalize_xy(x, y)
    return upsert_note(
        session,
        found['map'],
        x=xi,
        y=yi,
        text=found['text'],
        title=found['title'],
        note_id=found['id'],
    )


def delete_note(session, note_id: str, map_name: Optional[str] = None) -> bool:
    nid = str(note_id or '').strip()
    if not nid:
        return False
    store = _ensure_store(session)
    keys = [_normalize_map_name(map_name)] if map_name else list(store.keys())
    removed = False
    for key in keys:
        rows = store.get(key)
        if not isinstance(rows, list):
            continue
        kept = [row for row in rows if not (isinstance(row, dict) and str(row.get('id') or '') == nid)]
        if len(kept) != len(rows):
            store[key] = kept
            removed = True
            if not kept:
                store.pop(key, None)
    return removed
