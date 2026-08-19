# Player and campaign notes (notebook)

Login-level notes, journals, folders, and uploaded files. They belong to a **player account** or the **campaign**, not to a PlayerCharacter or NPC.

Character encounter journals stay on the PC (`/character/<uid>/journal`). Map-square pins stay in [DM_NOTES.md](DM_NOTES.md) and appear as the **Map Pins** tab inside this panel for the dungeon master.

## Who sees what

| Notebook | Who can read/write | LLM / MCP |
|---|---|---|
| **My Notes** (`scope=player`) | That login only (DM may inspect via MCP with `owner=`) | Not injected into NPC prompts |
| **Campaign** (`scope=campaign`) | DM only, until a document is **shared** | `list_campaign_notes` / `get_campaign_note` / `dm.notebook` |
| **Shared view** | Named recipients (popup on their VTT) | n/a |

Shared views are live snapshots of the current document. Recipients cannot edit the source.

## Using the panel

A **Notes** handle sits on the right edge of the map. The hamburger **Notes** item toggles the same panel. For the DM:

- **Map Pins** in the Authoring menu opens the pins tab (the old floating DM Notes list is embedded there).
- **AI Assistant** (Authoring menu, or the **Assistant** tab) embeds the DM assistant chat in this panel. The old floating window and corner toggle are gone; the DM Console still has its own assistant copy.

- **+ Note**, **+ Folder**, **Upload** — create objects in the current folder (or the selected folder).
- **Search** and **Sort** (manual / name / updated / created / type).
- Drag a row onto a folder (or the empty tree) to move it. Order in Manual sort is persisted immediately.
- Drag a note or file onto a map square to drop an **owner-only pin**. Only you see it. Click the pin to open that notebook entry; right-click to remove the pin (the note stays). Dropping the same note on another square of the same map moves the pin.
- Double-click a note or file to open the viewer. Right-click for Open / Rename / Delete.
- Notes use a Markdown-oriented editor (bold, lists, headings, preview/split). Changes autosave to SQLite.
- **Share** on an open document sends a popup to selected (or all online) players.

Allowed uploads: images (`png`, `jpg`, `gif`, `webp`), documents (`pdf`, `txt`, `md`, `csv`, `json`, `doc`/`docx`, `odt`, `rtf`), and short audio (`mp3`, `ogg`, `wav`). Max 15 MB.

## Storage

Files live next to campaign saves (not in map YAML, not on the character entity):

```
saves/<campaign>/notebook.sqlite
saves/<campaign>/notebook_files/
```

Writes commit immediately (SQLite WAL). Campaign reset of `save_*.yml` does **not** delete the notebook (same rule as `campaign_logs.sqlite`).

## HTTP API (logged-in)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/notebook?scope=player\|campaign&q=&sort=&order=` | Tree (folders + items) |
| `GET` | `/notebook/search?q=` | Flat search |
| `POST` | `/notebook/folders` | Create folder `{name, parent_id?, scope?}` |
| `PATCH` | `/notebook/folders/<id>` | Rename / move folder |
| `DELETE` | `/notebook/folders/<id>` | Delete folder and contents |
| `POST` | `/notebook/items` | Create note JSON, or multipart file upload |
| `GET` | `/notebook/items/<id>` | Note body or file metadata |
| `PATCH` | `/notebook/items/<id>` | Update title/content/folder |
| `DELETE` | `/notebook/items/<id>` | Delete item |
| `GET` | `/notebook/items/<id>/file` | File bytes (`?share=` for recipients, `?download=1`) |
| `POST` | `/notebook/move` | `{type, id, folder_id}` |
| `POST` | `/notebook/reorder` | `{folder_id, ordered: [{type, id}, …]}` |
| `GET` | `/notebook/recipients` | Share picker |
| `POST` | `/notebook/items/<id>/share` | `{usernames, all?}` |
| `GET` | `/notebook/map_links?map_name=` | Owner-only map pins linking to notebook items |
| `POST` | `/notebook/map_links` | Upsert pin `{item_id, map_name, x, y}` (one pin per note per map for this login) |
| `DELETE` | `/notebook/map_links/<id>` | Remove pin (does not delete the note) |

Socket events: `notebook_changed` (tree refresh; no body text), `notebook_share` (popup; payload is share id + title, not the full document), `notebook_map_links_changed` (owner-only pin refresh; map name only).

## MCP / DM LLM

`dm.notebook` with `op`:

- `list` / `search` / `get` / `create` / `update` / `delete` / `mkdir` / `move` / `share`

Default `scope` is `campaign`. For a player notebook pass `scope=player` and `owner=<username>`. Do not put this on `npc.*`.

DM assistant helpers: `list_campaign_notes`, `search_campaign_notes`, `get_campaign_note`. The generic `mcp("dm.notebook", {…})` bridge also works.

## Distinction from other features

- **Character journal** — per-PC encounter log and personal entries on the entity.
- **DM map pins** (`dm.note`) — squares on the current map. See [DM_NOTES.md](DM_NOTES.md).
- **AI DM Assistant** — chat in the Notes **Assistant** tab (and a copy in the DM Console). Not stored in the notebook SQLite DB.
- **`map_annotations`** — YAML landmarks for NPC navigation.
- **Object `notes`** — inspectable flavor on map objects.
