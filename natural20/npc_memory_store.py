"""Campaign-persisted long-term memory items for NPC entities.

Storage layout (under the active campaign ``root_path``)::

    npc_memories/
      <entity_uid>.json

Each file holds all memories for one entity. Files are human-editable JSON.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_MEMORY_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{8,64}$')


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_tags(raw) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(';', ',').split(',')]
        return [part for part in parts if part]
    if isinstance(raw, (list, tuple)):
        return [str(part).strip() for part in raw if str(part).strip()]
    return []


class NpcMemoryStore:
    """File-backed CRUD store for NPC memory items."""

    def __init__(self, campaign_root: str):
        self.campaign_root = os.path.abspath(campaign_root or '.')
        self.memories_dir = os.path.join(self.campaign_root, 'npc_memories')
        os.makedirs(self.memories_dir, exist_ok=True)
        self._lock = threading.RLock()

    def _entity_path(self, entity_uid: str) -> str:
        safe_uid = re.sub(r'[^a-zA-Z0-9_.-]+', '_', str(entity_uid or '').strip())
        if not safe_uid:
            raise ValueError('entity_uid is required')
        return os.path.join(self.memories_dir, f'{safe_uid}.json')

    def _load_entity_file(self, entity_uid: str) -> Dict[str, Any]:
        path = self._entity_path(entity_uid)
        if not os.path.isfile(path):
            return {'entity_uid': str(entity_uid), 'updated_at': None, 'items': []}
        with open(path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return {'entity_uid': str(entity_uid), 'updated_at': None, 'items': []}
        items = payload.get('items') or []
        if not isinstance(items, list):
            items = []
        return {
            'entity_uid': str(payload.get('entity_uid') or entity_uid),
            'updated_at': payload.get('updated_at'),
            'items': items,
        }

    def _save_entity_file(self, entity_uid: str, payload: Dict[str, Any]) -> None:
        path = self._entity_path(entity_uid)
        payload = dict(payload)
        payload['entity_uid'] = str(entity_uid)
        payload['updated_at'] = _utc_now_iso()
        tmp_path = f'{path}.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
        os.replace(tmp_path, path)

    def list_entity_uids(self) -> List[str]:
        with self._lock:
            uids = []
            for name in sorted(os.listdir(self.memories_dir)):
                if not name.endswith('.json'):
                    continue
                uids.append(name[:-5])
            return uids

    def list_summaries(
        self,
        entity_uid: str,
        *,
        limit: int = 10,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            payload = self._load_entity_file(entity_uid)
            items = [item for item in payload['items'] if isinstance(item, dict)]
            if query:
                needle = query.strip().lower()
                if needle:
                    items = [
                        item for item in items
                        if needle in str(item.get('title', '')).lower()
                        or needle in str(item.get('summary', '')).lower()
                        or needle in str(item.get('body', '')).lower()
                        or any(needle in str(tag).lower() for tag in (item.get('tags') or []))
                    ]
            items.sort(
                key=lambda item: (
                    int(item.get('importance') or 0),
                    int(item.get('game_time') or 0),
                    str(item.get('updated_at') or item.get('created_at') or ''),
                ),
                reverse=True,
            )
            summaries = []
            for item in items[: max(1, int(limit or 10))]:
                summaries.append(self._summary_row(item))
            return summaries

    def get(self, entity_uid: str, memory_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            payload = self._load_entity_file(entity_uid)
            for item in payload['items']:
                if isinstance(item, dict) and str(item.get('id')) == str(memory_id):
                    return dict(item)
            return None

    def find(self, memory_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for entity_uid in self.list_entity_uids():
                item = self.get(entity_uid, memory_id)
                if item is not None:
                    result = dict(item)
                    result['entity_uid'] = entity_uid
                    return result
            return None

    def create(
        self,
        entity_uid: str,
        *,
        title: str,
        summary: Optional[str] = None,
        body: Optional[str] = None,
        tags=None,
        importance: int = 3,
        game_time: Optional[int] = None,
        source: str = 'manual',
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        title = str(title or '').strip()
        if not title:
            raise ValueError('title is required')

        summary_text = str(summary or title).strip()
        body_text = str(body or summary_text).strip()
        now = _utc_now_iso()
        memory_id = uuid.uuid4().hex[:12]

        item = {
            'id': memory_id,
            'title': title[:200],
            'summary': summary_text[:500],
            'body': body_text[:8000],
            'tags': _normalize_tags(tags),
            'importance': max(1, min(5, int(importance or 3))),
            'game_time': int(game_time or 0),
            'created_at': now,
            'updated_at': now,
            'source': str(source or 'manual'),
            'created_by': str(created_by or 'unknown'),
        }

        with self._lock:
            payload = self._load_entity_file(entity_uid)
            payload['items'].append(item)
            self._save_entity_file(entity_uid, payload)
        return dict(item)

    def update(
        self,
        entity_uid: str,
        memory_id: str,
        *,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        body: Optional[str] = None,
        tags=None,
        importance: Optional[int] = None,
        game_time: Optional[int] = None,
        source: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            payload = self._load_entity_file(entity_uid)
            for index, item in enumerate(payload['items']):
                if not isinstance(item, dict) or str(item.get('id')) != str(memory_id):
                    continue
                updated = dict(item)
                if title is not None:
                    updated['title'] = str(title).strip()[:200]
                if summary is not None:
                    updated['summary'] = str(summary).strip()[:500]
                if body is not None:
                    updated['body'] = str(body).strip()[:8000]
                if tags is not None:
                    updated['tags'] = _normalize_tags(tags)
                if importance is not None:
                    updated['importance'] = max(1, min(5, int(importance)))
                if game_time is not None:
                    updated['game_time'] = int(game_time)
                if source is not None:
                    updated['source'] = str(source)
                updated['updated_at'] = _utc_now_iso()
                if updated_by:
                    updated['updated_by'] = str(updated_by)
                payload['items'][index] = updated
                self._save_entity_file(entity_uid, payload)
                return dict(updated)
            return None

    def delete(self, entity_uid: str, memory_id: str) -> bool:
        with self._lock:
            payload = self._load_entity_file(entity_uid)
            original_len = len(payload['items'])
            payload['items'] = [
                item for item in payload['items']
                if not (isinstance(item, dict) and str(item.get('id')) == str(memory_id))
            ]
            if len(payload['items']) == original_len:
                return False
            self._save_entity_file(entity_uid, payload)
            return True

    def format_context_summary(self, entity_uid: str, *, limit: int = 8) -> str:
        summaries = self.list_summaries(entity_uid, limit=limit)
        if not summaries:
            return ''
        lines = ['Recent memories (use [RECALL: id=<id>] or [RECALL: query=...] for details):']
        for item in summaries:
            tags = item.get('tags') or []
            tag_text = f" tags={','.join(tags)}" if tags else ''
            lines.append(
                f"- [{item['id']}] {item.get('title')}: {item.get('summary')}{tag_text}"
            )
        return '\n'.join(lines) + '\n'

    def format_recall_detail(self, item: Dict[str, Any]) -> str:
        tags = item.get('tags') or []
        tag_text = ', '.join(tags) if tags else 'none'
        return (
            f"[MEMORY id={item.get('id')}] {item.get('title')}\n"
            f"Summary: {item.get('summary')}\n"
            f"Details: {item.get('body')}\n"
            f"Tags: {tag_text}; importance: {item.get('importance')}; "
            f"game_time: {item.get('game_time')}"
        )

    @staticmethod
    def _summary_row(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'id': item.get('id'),
            'title': item.get('title'),
            'summary': item.get('summary'),
            'tags': list(item.get('tags') or []),
            'importance': item.get('importance'),
            'game_time': item.get('game_time'),
            'created_at': item.get('created_at'),
            'updated_at': item.get('updated_at'),
            'source': item.get('source'),
        }
