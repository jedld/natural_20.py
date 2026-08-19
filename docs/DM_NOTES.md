# DM notes (play-time map pins)

Private reminders the dungeon master can drop on any map square **during play**. They are not landmarks and they are not player-facing object notes.

## Visibility

DM notes are **DM-only**:

- Rendered only in the DM browser (script is not loaded for PCs).
- HTTP routes require the DM role (`GET/POST /dm/notes`, `POST /dm/notes/move`, `DELETE /dm/notes/<id>`).
- Socket payloads (`dm_notes_changed`) carry the map name only — never note text.
- They live in `session.session_state['dm_notes']`, so they save/load with the game but are **not** written to map YAML.
- They are **not** `map_annotations`. NPC movement, conversation RAG, `npc.get_location`, and `npc.query_area` never read this store.

PCs and NPCs cannot see the pins, the panel, or the note text.

## Using them

Log in as DM. Map pins live in the **Notes** panel on the right (**Map Pins** tab). The hamburger **Map Pins** item opens that tab. Minimized local chat still docks in the bottom-right chrome stack.

- **+ Note**, then click a square — or **Alt+click** a square — to add a pin.
- Click a pin or a list row to edit.
- **Esc** cancels placement mode.

Login-level campaign notes (folders, Markdown, uploads, sharing) are a different store. See [NOTEBOOK.md](NOTEBOOK.md).

Notes persist across save/load. They are per map and use that map’s local grid coordinates (including stacked floor overlays).

## HTTP API (DM)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/dm/notes?map_name=` | List notes on a map (defaults to the DM’s current map) |
| `POST` | `/dm/notes` | Create/update `{map_name, x, y, text, title?, id?}` |
| `POST` | `/dm/notes/move` | Reposition `{id, x, y, map_name?}` |
| `DELETE` | `/dm/notes/<id>` | Remove a note |

## MCP

`dm.note` with `op`:

- `list` — optional `map_name`
- `upsert` — `x`, `y`, `text`, optional `title`, `note_id`, `map_name`
- `move` — `note_id`, `x`, `y`
- `delete` — `note_id`

This tool is DM-privileged. Do not expose it on `npc.*` or `world.*`.

## Storage

```python
session.session_state['dm_notes'] = {
  'tavern': [
    {'id': '...', 'map': 'tavern', 'x': 8, 'y': 12, 'title': '...', 'text': '...', ...},
  ],
}
```

## Distinction from other features

- **`map_annotations`** — campaign YAML landmarks for NPC navigation and LLM place context. See [MAP_ANNOTATIONS.md](MAP_ANNOTATIONS.md).
- **Object `notes` / `show-note-btn`** — inspectable object flavor on the map (perception DCs, etc.).
- **Object `annotations`** — NPC-only staff markings on containers/objects.
- **Character journal** — per-PC notes, not map pins.
- **Campaign/player notebook** — login- and campaign-level folders/files in SQLite. Dragging a notebook item onto the map creates an **owner-only** pin that opens that entry. See [NOTEBOOK.md](NOTEBOOK.md).
