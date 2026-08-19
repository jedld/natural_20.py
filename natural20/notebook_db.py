"""Player- and campaign-level notes/journals backed by SQLite.

These records belong to a login (player) or the campaign (DM), not to a
PlayerCharacter or NPC entity. Character journals remain on the entity.
Map pins remain in ``session.session_state['dm_notes']``.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCOPES = frozenset({'player', 'campaign'})
ITEM_KINDS = frozenset({'note', 'file'})
SORT_FIELDS = {
    'title': 'title COLLATE NOCASE',
    'name': 'title COLLATE NOCASE',
    'updated': 'updated_at',
    'created': 'created_at',
    'kind': 'kind, title COLLATE NOCASE',
    'order': 'sort_order, title COLLATE NOCASE',
}

CAMPAIGN_OWNER = 'campaign'
_MAX_TITLE = 200
_MAX_FOLDER_NAME = 120
_MAX_NOTE_CHARS = 500_000
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024
_SAFE_FILENAME = re.compile(r'[^A-Za-z0-9._-]+')

ALLOWED_EXTENSIONS = frozenset({
    'png', 'jpg', 'jpeg', 'gif', 'webp',
    'pdf', 'txt', 'md', 'csv', 'json',
    'doc', 'docx', 'odt', 'rtf',
    'mp3', 'ogg', 'wav',
})

IMAGE_EXTENSIONS = frozenset({'png', 'jpg', 'jpeg', 'gif', 'webp'})
IMAGE_MIMES = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _clamp(value: Any, limit: int) -> str:
    return str(value or '').strip()[:limit]


def _safe_filename(name: str) -> str:
    base = os.path.basename(str(name or 'file'))
    cleaned = _SAFE_FILENAME.sub('_', base).strip('._') or 'file'
    return cleaned[:180]


def extension_of(filename: str) -> str:
    return os.path.splitext(str(filename or ''))[1].lstrip('.').lower()


def guess_mime(filename: str, fallback: Optional[str] = None) -> str:
    ext = extension_of(filename)
    if ext in IMAGE_MIMES:
        return IMAGE_MIMES[ext]
    mapping = {
        'pdf': 'application/pdf',
        'txt': 'text/plain',
        'md': 'text/markdown',
        'csv': 'text/csv',
        'json': 'application/json',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'odt': 'application/vnd.oasis.opendocument.text',
        'rtf': 'application/rtf',
        'mp3': 'audio/mpeg',
        'ogg': 'audio/ogg',
        'wav': 'audio/wav',
    }
    return mapping.get(ext) or fallback or 'application/octet-stream'


class NotebookError(ValueError):
    """User-facing notebook validation error."""


class NotebookDB:
    """CRUD store for player/campaign notebooks (folders, notes, files)."""

    def __init__(self, db_path: str, files_dir: Optional[str] = None):
        self.db_path = os.path.abspath(db_path)
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if files_dir:
            self.files_dir = os.path.abspath(files_dir)
        else:
            self.files_dir = os.path.join(parent or os.getcwd(), 'notebook_files')
        os.makedirs(self.files_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('PRAGMA synchronous = NORMAL')
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS folders (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        parent_id TEXT,
                        name TEXT NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(parent_id) REFERENCES folders(id) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS items (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        folder_id TEXT,
                        kind TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT,
                        mime_type TEXT,
                        filename TEXT,
                        storage_name TEXT,
                        file_size INTEGER,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        created_by TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE SET NULL
                    );
                    CREATE TABLE IF NOT EXISTS shares (
                        id TEXT PRIMARY KEY,
                        item_id TEXT NOT NULL,
                        from_username TEXT NOT NULL,
                        to_username TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_nb_folders_owner
                        ON folders(scope, owner, parent_id, sort_order);
                    CREATE INDEX IF NOT EXISTS idx_nb_items_owner
                        ON items(scope, owner, folder_id, sort_order);
                    CREATE INDEX IF NOT EXISTS idx_nb_items_title
                        ON items(scope, owner, title);
                    CREATE INDEX IF NOT EXISTS idx_nb_shares_to
                        ON shares(to_username, created_at);
                    CREATE TABLE IF NOT EXISTS map_links (
                        id TEXT PRIMARY KEY,
                        item_id TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        map TEXT NOT NULL,
                        x INTEGER NOT NULL,
                        y INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_nb_map_links_owner_map
                        ON map_links(owner, map);
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_nb_map_links_unique
                        ON map_links(owner, item_id, map);
                    """
                )
                conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {key: row[key] for key in row.keys()}

    def _folder_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = self._row_to_dict(row)
        data['type'] = 'folder'
        return data

    def _item_dict(self, row: sqlite3.Row, *, include_content: bool = False) -> Dict[str, Any]:
        data = self._row_to_dict(row)
        data['type'] = 'item'
        if not include_content:
            data.pop('content', None)
        if data.get('kind') == 'file':
            data['file_url'] = f"/notebook/items/{data['id']}/file"
            data['is_image'] = extension_of(data.get('filename') or '') in IMAGE_EXTENSIONS
        return data

    def normalize_scope_owner(self, scope: str, owner: Optional[str], *, is_dm: bool) -> Tuple[str, str]:
        kind = str(scope or '').strip().lower()
        if kind not in SCOPES:
            raise NotebookError('scope must be player or campaign')
        if kind == 'campaign':
            if not is_dm:
                raise NotebookError('campaign notes are DM-only')
            return 'campaign', CAMPAIGN_OWNER
        owner_id = str(owner or '').strip().lower()
        if not owner_id:
            raise NotebookError('owner is required for player notes')
        return 'player', owner_id

    def tree(
        self,
        scope: str,
        owner: str,
        *,
        sort: str = 'order',
        order: str = 'asc',
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        sort_sql = SORT_FIELDS.get(str(sort or 'order').lower(), SORT_FIELDS['order'])
        direction = 'DESC' if str(order or 'asc').lower() == 'desc' else 'ASC'
        q = str(query or '').strip()
        needle = q.lower()
        with self._lock:
            with self._connect() as conn:
                folders = [
                    self._folder_dict(row)
                    for row in conn.execute(
                        """
                        SELECT * FROM folders
                        WHERE scope = ? AND owner = ?
                        ORDER BY sort_order ASC, name COLLATE NOCASE ASC
                        """,
                        (scope, owner),
                    ).fetchall()
                ]
                if needle:
                    items = [
                        self._item_dict(row)
                        for row in conn.execute(
                            f"""
                            SELECT * FROM items
                            WHERE scope = ? AND owner = ?
                              AND (
                                instr(lower(title), ?) > 0
                                OR instr(lower(COALESCE(filename, '')), ?) > 0
                                OR (kind = 'note' AND instr(lower(COALESCE(content, '')), ?) > 0)
                              )
                            ORDER BY {sort_sql} {direction}
                            """,
                            (scope, owner, needle, needle, needle),
                        ).fetchall()
                    ]
                else:
                    items = [
                        self._item_dict(row)
                        for row in conn.execute(
                            f"""
                            SELECT * FROM items
                            WHERE scope = ? AND owner = ?
                            ORDER BY {sort_sql} {direction}
                            """,
                            (scope, owner),
                        ).fetchall()
                    ]
        return {
            'scope': scope,
            'owner': owner,
            'folders': folders,
            'items': items,
            'sort': sort,
            'order': order,
            'query': q,
        }

    def search(
        self,
        scope: str,
        owner: str,
        query: str,
        *,
        limit: int = 50,
        sort: str = 'updated',
        order: str = 'desc',
    ) -> List[Dict[str, Any]]:
        tree = self.tree(scope, owner, sort=sort, order=order, query=query)
        return tree['items'][: max(1, min(int(limit or 50), 200))]

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        fid = str(folder_id or '').strip()
        if not fid:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute('SELECT * FROM folders WHERE id = ?', (fid,)).fetchone()
        return self._folder_dict(row) if row else None

    def get_item(self, item_id: str, *, include_content: bool = True) -> Optional[Dict[str, Any]]:
        iid = str(item_id or '').strip()
        if not iid:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute('SELECT * FROM items WHERE id = ?', (iid,)).fetchone()
        return self._item_dict(row, include_content=include_content) if row else None

    def _assert_parent(
        self,
        conn: sqlite3.Connection,
        scope: str,
        owner: str,
        parent_id: Optional[str],
    ) -> Optional[str]:
        if not parent_id:
            return None
        pid = str(parent_id).strip()
        row = conn.execute(
            'SELECT id, scope, owner FROM folders WHERE id = ?',
            (pid,),
        ).fetchone()
        if row is None:
            raise NotebookError('parent folder not found')
        if row['scope'] != scope or row['owner'] != owner:
            raise NotebookError('parent folder is in a different notebook')
        return pid

    def _next_sort(self, conn: sqlite3.Connection, table: str, scope: str, owner: str, parent_id: Optional[str]) -> int:
        parent_col = 'parent_id' if table == 'folders' else 'folder_id'
        if parent_id:
            row = conn.execute(
                f'SELECT COALESCE(MAX(sort_order), -1) AS m FROM {table} WHERE scope = ? AND owner = ? AND {parent_col} = ?',
                (scope, owner, parent_id),
            ).fetchone()
        else:
            row = conn.execute(
                f'SELECT COALESCE(MAX(sort_order), -1) AS m FROM {table} WHERE scope = ? AND owner = ? AND {parent_col} IS NULL',
                (scope, owner),
            ).fetchone()
        return int(row['m']) + 1

    def create_folder(
        self,
        scope: str,
        owner: str,
        name: str,
        *,
        parent_id: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> Dict[str, Any]:
        title = _clamp(name, _MAX_FOLDER_NAME)
        if not title:
            raise NotebookError('folder name is required')
        now = _utc_now_iso()
        fid = _new_id()
        with self._lock:
            with self._connect() as conn:
                pid = self._assert_parent(conn, scope, owner, parent_id)
                order = int(sort_order) if sort_order is not None else self._next_sort(conn, 'folders', scope, owner, pid)
                conn.execute(
                    """
                    INSERT INTO folders (id, scope, owner, parent_id, name, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (fid, scope, owner, pid, title, order, now, now),
                )
                conn.commit()
                row = conn.execute('SELECT * FROM folders WHERE id = ?', (fid,)).fetchone()
        return self._folder_dict(row)

    def update_folder(
        self,
        folder_id: str,
        *,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
        sort_order: Optional[int] = None,
        move_parent: bool = False,
    ) -> Dict[str, Any]:
        folder = self.get_folder(folder_id)
        if folder is None:
            raise NotebookError('folder not found')
        updates: Dict[str, Any] = {'updated_at': _utc_now_iso()}
        if name is not None:
            title = _clamp(name, _MAX_FOLDER_NAME)
            if not title:
                raise NotebookError('folder name is required')
            updates['name'] = title
        if sort_order is not None:
            updates['sort_order'] = int(sort_order)
        with self._lock:
            with self._connect() as conn:
                if move_parent:
                    new_parent = self._assert_parent(conn, folder['scope'], folder['owner'], parent_id)
                    if new_parent == folder['id']:
                        raise NotebookError('folder cannot contain itself')
                    if new_parent and self._is_descendant(conn, folder['id'], new_parent):
                        raise NotebookError('cannot move a folder into its descendant')
                    updates['parent_id'] = new_parent
                    if sort_order is None:
                        updates['sort_order'] = self._next_sort(
                            conn, 'folders', folder['scope'], folder['owner'], new_parent
                        )
                assignments = ', '.join(f'{k} = ?' for k in updates)
                values = list(updates.values()) + [folder['id']]
                conn.execute(f'UPDATE folders SET {assignments} WHERE id = ?', values)
                conn.commit()
                row = conn.execute('SELECT * FROM folders WHERE id = ?', (folder['id'],)).fetchone()
        return self._folder_dict(row)

    def _is_descendant(self, conn: sqlite3.Connection, ancestor_id: str, candidate_id: str) -> bool:
        current = candidate_id
        seen = set()
        while current:
            if current == ancestor_id:
                return True
            if current in seen:
                break
            seen.add(current)
            row = conn.execute('SELECT parent_id FROM folders WHERE id = ?', (current,)).fetchone()
            current = row['parent_id'] if row else None
        return False

    def delete_folder(self, folder_id: str) -> bool:
        folder = self.get_folder(folder_id)
        if folder is None:
            return False
        ids = self._descendant_folder_ids(folder_id)
        ids.add(folder_id)
        items: List[Dict[str, Any]] = []
        with self._lock:
            with self._connect() as conn:
                placeholders = ','.join('?' for _ in ids)
                items = [
                    self._item_dict(row, include_content=False)
                    for row in conn.execute(
                        f'SELECT * FROM items WHERE folder_id IN ({placeholders})',
                        tuple(ids),
                    ).fetchall()
                ]
                conn.execute(f'DELETE FROM items WHERE folder_id IN ({placeholders})', tuple(ids))
                conn.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
                conn.commit()
        for item in items:
            self._delete_stored_file(item)
        return True

    def _descendant_folder_ids(self, folder_id: str) -> set[str]:
        found: set[str] = set()
        with self._lock:
            with self._connect() as conn:
                frontier = [folder_id]
                while frontier:
                    current = frontier.pop()
                    rows = conn.execute(
                        'SELECT id FROM folders WHERE parent_id = ?',
                        (current,),
                    ).fetchall()
                    for row in rows:
                        cid = row['id']
                        if cid not in found:
                            found.add(cid)
                            frontier.append(cid)
        return found

    def create_note(
        self,
        scope: str,
        owner: str,
        title: str,
        *,
        content: str = '',
        folder_id: Optional[str] = None,
        created_by: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> Dict[str, Any]:
        heading = _clamp(title, _MAX_TITLE) or 'Untitled note'
        body = str(content or '')[:_MAX_NOTE_CHARS]
        now = _utc_now_iso()
        iid = _new_id()
        with self._lock:
            with self._connect() as conn:
                fid = self._assert_parent(conn, scope, owner, folder_id)
                order = int(sort_order) if sort_order is not None else self._next_sort(conn, 'items', scope, owner, fid)
                conn.execute(
                    """
                    INSERT INTO items (
                        id, scope, owner, folder_id, kind, title, content,
                        mime_type, filename, storage_name, file_size, sort_order,
                        created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'note', ?, ?, 'text/markdown', NULL, NULL, NULL, ?, ?, ?, ?)
                    """,
                    (iid, scope, owner, fid, heading, body, order, created_by, now, now),
                )
                conn.commit()
                row = conn.execute('SELECT * FROM items WHERE id = ?', (iid,)).fetchone()
        return self._item_dict(row, include_content=True)

    def update_item(
        self,
        item_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        folder_id: Optional[str] = None,
        sort_order: Optional[int] = None,
        move_folder: bool = False,
    ) -> Dict[str, Any]:
        item = self.get_item(item_id, include_content=True)
        if item is None:
            raise NotebookError('item not found')
        updates: Dict[str, Any] = {'updated_at': _utc_now_iso()}
        if title is not None:
            heading = _clamp(title, _MAX_TITLE)
            if not heading:
                raise NotebookError('title is required')
            updates['title'] = heading
        if content is not None:
            if item.get('kind') != 'note':
                raise NotebookError('only notes have editable text content')
            updates['content'] = str(content)[:_MAX_NOTE_CHARS]
        if sort_order is not None:
            updates['sort_order'] = int(sort_order)
        with self._lock:
            with self._connect() as conn:
                if move_folder:
                    new_folder = self._assert_parent(conn, item['scope'], item['owner'], folder_id)
                    updates['folder_id'] = new_folder
                    if sort_order is None:
                        updates['sort_order'] = self._next_sort(
                            conn, 'items', item['scope'], item['owner'], new_folder
                        )
                assignments = ', '.join(f'{k} = ?' for k in updates)
                values = list(updates.values()) + [item['id']]
                conn.execute(f'UPDATE items SET {assignments} WHERE id = ?', values)
                conn.commit()
                row = conn.execute('SELECT * FROM items WHERE id = ?', (item['id'],)).fetchone()
        return self._item_dict(row, include_content=True)

    def create_file(
        self,
        scope: str,
        owner: str,
        original_filename: str,
        data: bytes,
        *,
        folder_id: Optional[str] = None,
        created_by: Optional[str] = None,
        mime_type: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        filename = _safe_filename(original_filename)
        ext = extension_of(filename)
        if ext not in ALLOWED_EXTENSIONS:
            raise NotebookError(f'file type .{ext or "unknown"} is not allowed')
        payload = data or b''
        if len(payload) > _MAX_UPLOAD_BYTES:
            raise NotebookError(f'file exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit')
        if not payload:
            raise NotebookError('uploaded file is empty')
        iid = _new_id()
        storage_name = f'{iid}_{filename}'
        dest = os.path.join(self.files_dir, storage_name)
        os.makedirs(self.files_dir, exist_ok=True)
        with open(dest, 'wb') as handle:
            handle.write(payload)
        now = _utc_now_iso()
        heading = _clamp(title, _MAX_TITLE) or os.path.splitext(filename)[0] or filename
        mime = guess_mime(filename, mime_type)
        try:
            with self._lock:
                with self._connect() as conn:
                    fid = self._assert_parent(conn, scope, owner, folder_id)
                    order = self._next_sort(conn, 'items', scope, owner, fid)
                    conn.execute(
                        """
                        INSERT INTO items (
                            id, scope, owner, folder_id, kind, title, content,
                            mime_type, filename, storage_name, file_size, sort_order,
                            created_by, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 'file', ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            iid, scope, owner, fid, heading, mime, filename,
                            storage_name, len(payload), order, created_by, now, now,
                        ),
                    )
                    conn.commit()
                    row = conn.execute('SELECT * FROM items WHERE id = ?', (iid,)).fetchone()
        except Exception:
            try:
                os.remove(dest)
            except OSError:
                pass
            raise
        return self._item_dict(row, include_content=False)

    def file_path(self, item: Dict[str, Any]) -> Optional[str]:
        storage = str(item.get('storage_name') or '').strip()
        if not storage:
            return None
        path = os.path.abspath(os.path.join(self.files_dir, storage))
        files_root = os.path.abspath(self.files_dir)
        if not path.startswith(files_root + os.sep) and path != files_root:
            return None
        if not os.path.isfile(path):
            return None
        return path

    def _delete_stored_file(self, item: Dict[str, Any]) -> None:
        path = self.file_path(item)
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def delete_item(self, item_id: str) -> bool:
        item = self.get_item(item_id, include_content=False)
        if item is None:
            return False
        with self._lock:
            with self._connect() as conn:
                conn.execute('DELETE FROM items WHERE id = ?', (item['id'],))
                conn.commit()
        self._delete_stored_file(item)
        return True

    def reorder(
        self,
        scope: str,
        owner: str,
        *,
        folder_id: Optional[str],
        ordered: Iterable[Dict[str, str]],
    ) -> None:
        """Rewrite sort_order for nodes dropped into the same parent."""
        rows = list(ordered or [])
        now = _utc_now_iso()
        with self._lock:
            with self._connect() as conn:
                parent = self._assert_parent(conn, scope, owner, folder_id)
                for index, node in enumerate(rows):
                    kind = str(node.get('type') or node.get('kind') or '').strip()
                    nid = str(node.get('id') or '').strip()
                    if not nid:
                        continue
                    if kind == 'folder':
                        conn.execute(
                            """
                            UPDATE folders
                            SET parent_id = ?, sort_order = ?, updated_at = ?
                            WHERE id = ? AND scope = ? AND owner = ?
                            """,
                            (parent, index, now, nid, scope, owner),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE items
                            SET folder_id = ?, sort_order = ?, updated_at = ?
                            WHERE id = ? AND scope = ? AND owner = ?
                            """,
                            (parent, index, now, nid, scope, owner),
                        )
                conn.commit()

    def move_node(
        self,
        node_type: str,
        node_id: str,
        *,
        folder_id: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> Dict[str, Any]:
        kind = str(node_type or '').strip().lower()
        if kind == 'folder':
            return self.update_folder(
                node_id,
                parent_id=folder_id,
                sort_order=sort_order,
                move_parent=True,
            )
        return self.update_item(
            node_id,
            folder_id=folder_id,
            sort_order=sort_order,
            move_folder=True,
        )

    def create_shares(
        self,
        item_id: str,
        from_username: str,
        recipients: Iterable[str],
    ) -> List[Dict[str, Any]]:
        item = self.get_item(item_id, include_content=False)
        if item is None:
            raise NotebookError('item not found')
        sender = str(from_username or '').strip().lower()
        if not sender:
            raise NotebookError('from_username is required')
        created: List[Dict[str, Any]] = []
        now = _utc_now_iso()
        unique: List[str] = []
        seen = set()
        for name in recipients:
            target = str(name or '').strip().lower()
            if not target or target in seen:
                continue
            seen.add(target)
            unique.append(target)
        if not unique:
            raise NotebookError('at least one recipient is required')
        with self._lock:
            with self._connect() as conn:
                for target in unique:
                    sid = _new_id()
                    conn.execute(
                        """
                        INSERT INTO shares (id, item_id, from_username, to_username, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (sid, item['id'], sender, target, now),
                    )
                    created.append({
                        'id': sid,
                        'item_id': item['id'],
                        'from_username': sender,
                        'to_username': target,
                        'created_at': now,
                    })
                conn.commit()
        return created

    def get_share(self, share_id: str) -> Optional[Dict[str, Any]]:
        sid = str(share_id or '').strip()
        if not sid:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute('SELECT * FROM shares WHERE id = ?', (sid,)).fetchone()
        return self._row_to_dict(row) if row else None

    def shared_view(self, share_id: str, username: str) -> Dict[str, Any]:
        share = self.get_share(share_id)
        if share is None:
            raise NotebookError('share not found')
        user = str(username or '').strip().lower()
        target = str(share.get('to_username') or '').strip().lower()
        if target not in ('*', user) and user != str(share.get('from_username') or '').lower():
            raise NotebookError('not a recipient of this share')
        item = self.get_item(share['item_id'], include_content=True)
        if item is None:
            raise NotebookError('shared item no longer exists')
        return {
            'share': share,
            'item': item,
        }

    def campaign_summary(self, *, limit: int = 40, query: Optional[str] = None) -> Dict[str, Any]:
        """Compact listing for DM LLM / MCP (campaign notebook only)."""
        tree = self.tree('campaign', CAMPAIGN_OWNER, sort='updated', order='desc', query=query)
        folders = {row['id']: row['name'] for row in tree['folders']}
        items = []
        for item in tree['items'][: max(1, min(int(limit or 40), 200))]:
            folder_name = folders.get(item.get('folder_id')) if item.get('folder_id') else None
            preview = None
            if item.get('kind') == 'note':
                full = self.get_item(item['id'], include_content=True) or {}
                text = str(full.get('content') or '')
                preview = text[:400]
            items.append({
                'id': item['id'],
                'kind': item.get('kind'),
                'title': item.get('title'),
                'folder': folder_name,
                'folder_id': item.get('folder_id'),
                'updated_at': item.get('updated_at'),
                'preview': preview,
                'filename': item.get('filename'),
            })
        return {
            'scope': 'campaign',
            'folder_count': len(tree['folders']),
            'item_count': len(tree['items']),
            'items': items,
        }

    def _map_link_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = self._row_to_dict(row)
        data['type'] = 'map_link'
        data['x'] = int(data.get('x') or 0)
        data['y'] = int(data.get('y') or 0)
        return data

    def list_map_links(self, owner: str, map_name: Optional[str] = None) -> List[Dict[str, Any]]:
        owner_id = str(owner or '').strip().lower()
        if not owner_id:
            return []
        map_key = str(map_name or '').strip()
        sql = """
            SELECT ml.*, i.title, i.kind, i.scope AS item_scope, i.filename
            FROM map_links ml
            JOIN items i ON i.id = ml.item_id
            WHERE ml.owner = ?
        """
        params: List[Any] = [owner_id]
        if map_key:
            sql += ' AND ml.map = ?'
            params.append(map_key)
        sql += ' ORDER BY ml.map, ml.y, ml.x, i.title COLLATE NOCASE'
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        return [self._map_link_dict(row) for row in rows]

    def get_map_link(self, link_id: str) -> Optional[Dict[str, Any]]:
        lid = str(link_id or '').strip()
        if not lid:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT ml.*, i.title, i.kind, i.scope AS item_scope, i.filename
                    FROM map_links ml
                    JOIN items i ON i.id = ml.item_id
                    WHERE ml.id = ?
                    """,
                    (lid,),
                ).fetchone()
        return self._map_link_dict(row) if row else None

    def upsert_map_link(
        self,
        owner: str,
        item_id: str,
        map_name: str,
        x: Any,
        y: Any,
    ) -> Dict[str, Any]:
        owner_id = str(owner or '').strip().lower()
        if not owner_id:
            raise NotebookError('owner is required')
        item = self.get_item(item_id, include_content=False)
        if item is None:
            raise NotebookError('item not found')
        map_key = str(map_name or '').strip()
        if not map_key:
            raise NotebookError('map_name is required')
        try:
            xi, yi = int(x), int(y)
        except (TypeError, ValueError) as exc:
            raise NotebookError('x and y must be integers') from exc
        if xi < 0 or yi < 0:
            raise NotebookError('x and y must be >= 0')
        now = _utc_now_iso()
        with self._lock:
            with self._connect() as conn:
                existing = conn.execute(
                    """
                    SELECT id FROM map_links
                    WHERE owner = ? AND item_id = ? AND map = ?
                    """,
                    (owner_id, item['id'], map_key),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE map_links
                        SET x = ?, y = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (xi, yi, now, existing['id']),
                    )
                    link_id = existing['id']
                else:
                    link_id = _new_id()
                    conn.execute(
                        """
                        INSERT INTO map_links (
                            id, item_id, owner, map, x, y, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (link_id, item['id'], owner_id, map_key, xi, yi, now, now),
                    )
                conn.commit()
        saved = self.get_map_link(link_id)
        if saved is None:
            raise NotebookError('failed to save map link')
        return saved

    def delete_map_link(self, link_id: str, owner: Optional[str] = None) -> bool:
        link = self.get_map_link(link_id)
        if link is None:
            return False
        if owner and str(owner).strip().lower() != str(link.get('owner') or ''):
            raise NotebookError('not the owner of this map link')
        with self._lock:
            with self._connect() as conn:
                conn.execute('DELETE FROM map_links WHERE id = ?', (link['id'],))
                conn.commit()
        return True


def destroy_notebook_files(files_dir: str) -> None:
    """Remove uploaded notebook files (used by tests)."""
    if files_dir and os.path.isdir(files_dir):
        shutil.rmtree(files_dir, ignore_errors=True)
