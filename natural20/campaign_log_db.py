"""Per-campaign SQLite store for narrative and log-like text."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

CATEGORIES = frozenset({'combat', 'conversation', 'dm_assistant', 'journal'})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CampaignLogDB:
    """Append-only campaign log backed by SQLite (one file per campaign)."""

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        self._lock = threading.Lock()
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS log_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        content TEXT NOT NULL,
                        entity_uid TEXT,
                        character_name TEXT,
                        username TEXT,
                        title TEXT,
                        kind TEXT,
                        visibility_json TEXT,
                        metadata_json TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_log_entries_cat_created
                        ON log_entries(category, created_at);
                    CREATE INDEX IF NOT EXISTS idx_log_entries_character
                        ON log_entries(character_name, created_at);
                    """
                )
                conn.commit()

    def append(
        self,
        category: str,
        content: str,
        *,
        created_at: Optional[str] = None,
        entity_uid: Optional[str] = None,
        character_name: Optional[str] = None,
        username: Optional[str] = None,
        title: Optional[str] = None,
        kind: Optional[str] = None,
        visibility: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        if category not in CATEGORIES:
            raise ValueError(f'Unknown log category: {category}')
        text = str(content or '').strip()
        if not text:
            return 0
        row = {
            'category': category,
            'created_at': created_at or _utc_now_iso(),
            'content': text,
            'entity_uid': entity_uid,
            'character_name': character_name,
            'username': username,
            'title': title,
            'kind': kind,
            'visibility_json': json.dumps(visibility) if visibility is not None else None,
            'metadata_json': json.dumps(metadata) if metadata is not None else None,
        }
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO log_entries (
                        category, created_at, content, entity_uid, character_name,
                        username, title, kind, visibility_json, metadata_json
                    ) VALUES (
                        :category, :created_at, :content, :entity_uid, :character_name,
                        :username, :title, :kind, :visibility_json, :metadata_json
                    )
                    """,
                    row,
                )
                conn.commit()
                return int(cur.lastrowid or 0)

    def append_journal_entry(self, character_name: str, entry: Dict[str, Any]) -> int:
        if not character_name or not isinstance(entry, dict):
            return 0
        text = str(entry.get('text') or '').strip()
        if not text:
            return 0
        return self.append(
            'journal',
            text,
            created_at=entry.get('ts'),
            character_name=character_name,
            entity_uid=character_name,
            title=entry.get('title'),
            kind=entry.get('kind') or 'note',
            metadata={
                'id': entry.get('id'),
                'source': entry.get('source'),
                'map_name': entry.get('map_name'),
                'tags': entry.get('tags') or [],
            },
        )

    def append_conversation(
        self,
        *,
        speaker_uid: str,
        speaker_label: str,
        message: str,
        targets: Optional[List[str]] = None,
        target_labels: Optional[List[str]] = None,
        volume: Optional[str] = None,
        language: Optional[str] = None,
        username: Optional[str] = None,
        narrative: Optional[List[str]] = None,
    ) -> int:
        target_text = ', '.join(target_labels or targets or []) or 'nearby'
        header = f'{speaker_label} → {target_text}'
        if volume:
            header += f' ({volume})'
        if language:
            header += f' [{language}]'
        body = f'{header}: {message}'
        if narrative:
            body += '\n' + '\n'.join(str(n) for n in narrative if n)
        return self.append(
            'conversation',
            body,
            entity_uid=speaker_uid,
            username=username,
            kind=volume,
            metadata={
                'targets': targets or [],
                'target_labels': target_labels or [],
                'language': language,
            },
        )

    def append_dm_turn(self, role: str, content: str, *, username: Optional[str] = None) -> int:
        role_key = str(role or '').strip().lower()
        if role_key not in ('user', 'assistant'):
            return 0
        return self.append(
            'dm_assistant',
            str(content or '').strip(),
            username=username,
            kind=role_key,
        )

    def list_entries(
        self,
        category: Optional[str] = None,
        *,
        limit: int = 500,
        offset: int = 0,
        character_name: Optional[str] = None,
        entity_uid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses = []
        params: List[Any] = []
        if category:
            clauses.append('category = ?')
            params.append(category)
        if character_name:
            clauses.append('character_name = ?')
            params.append(character_name)
        if entity_uid:
            clauses.append('entity_uid = ?')
            params.append(entity_uid)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
        sql = (
            f'SELECT * FROM log_entries {where} '
            f'ORDER BY id ASC LIMIT ? OFFSET ?'
        )
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def dm_assistant_history_for_llm(self, limit: int = 200) -> List[Dict[str, str]]:
        rows = self.list_entries('dm_assistant', limit=limit)
        history: List[Dict[str, str]] = []
        for row in rows:
            role = row.get('kind') or 'user'
            if role not in ('user', 'assistant'):
                continue
            content = str(row.get('content') or '').strip()
            if not content:
                continue
            if role == 'user' and '[FUNCTION_CALL:' in content:
                continue
            history.append({'role': role, 'content': content})
        return history

    def combat_log_snapshot(self, limit: int = 1000) -> List[Dict[str, Any]]:
        rows = self.list_entries('combat', limit=limit)
        snapshot = []
        for row in rows:
            visibility = None
            raw_vis = row.get('visibility_json')
            if raw_vis:
                try:
                    visibility = json.loads(raw_vis)
                except Exception:
                    visibility = None
            snapshot.append({
                'timestamp': row.get('created_at', ''),
                'message': row.get('content', ''),
                'visibility': visibility,
            })
        return snapshot

    def counts_by_category(self) -> Dict[str, int]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    'SELECT category, COUNT(*) AS n FROM log_entries GROUP BY category'
                ).fetchall()
        return {str(row['category']): int(row['n']) for row in rows}

    def clear_all(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute('DELETE FROM log_entries')
                conn.commit()

    def clear_category(self, category: str) -> None:
        if category not in CATEGORIES:
            raise ValueError(f'Unknown log category: {category}')
        with self._lock:
            with self._connect() as conn:
                conn.execute('DELETE FROM log_entries WHERE category = ?', (category,))
                conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {key: row[key] for key in row.keys()}
