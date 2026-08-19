# MCP surface (DM tools for Cursor, Claude, and other hosts)

Natural20 exposes Dungeon Master tools over the [Model Context Protocol](https://modelcontextprotocol.io/) so an external agent can inspect and mutate a **running** webapp instance.

The game state lives in the Flask process. Clients must talk to that process (Streamable HTTP), or to a stdio proxy that forwards JSON-RPC to it.

## Prerequisites

1. Start the webapp as usual (`./start_web.sh <campaign>`).
2. Set a shared secret in `n20-webapp/webapp/.env` (or the environment):

```bash
export N20_MCP_DM_TOKEN="a-long-random-secret"
```

Without the token, only a logged-in DM browser session can call `/mcp/*`.

The token is DM-equivalent: every `world.*`, `dm.*`, `actions.*`, and `npc.*` tool runs with admin privilege.

## Connect Cursor / Claude Code (Streamable HTTP)

Project `.cursor/mcp.json` or user `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "natural20": {
      "url": "http://127.0.0.1:5001/mcp",
      "headers": {
        "Authorization": "Bearer ${env:N20_MCP_DM_TOKEN}"
      }
    }
  }
}
```

Claude Code (`~/.claude.json` / MCP settings) uses the same `url` + `headers` shape. Point `url` at whatever host/port the webapp is bound to (default `5001`).

Do not commit the raw token. Prefer `${env:N20_MCP_DM_TOKEN}` (Cursor) or the host's env-var interpolation.

## Connect Claude Desktop (stdio)

Claude Desktop launches a local subprocess. Use the stdio proxy, which forwards newline-delimited JSON-RPC to the running webapp:

```json
{
  "mcpServers": {
    "natural20": {
      "command": "python",
      "args": ["-m", "webapp.mcp.stdio"],
      "env": {
        "PYTHONPATH": "/path/to/natural_20.py/n20-webapp",
        "N20_MCP_URL": "http://127.0.0.1:5001/mcp",
        "N20_MCP_DM_TOKEN": "<same token as the webapp>"
      }
    }
  }
}
```

`PYTHONPATH` must include the `n20-webapp` directory (the parent of the `webapp` package). The engine repo root should also be on `PYTHONPATH` if you import `natural20` from the same environment.

## Protocol

`POST /mcp` is Streamable HTTP JSON-RPC (`Content-Type: application/json`).

| Era | How clients start | Methods |
|---|---|---|
| **2026-07-28** (preferred) | No handshake. Optional `server/discover`. Requires `MCP-Protocol-Version`, `Mcp-Method`, and (for `tools/call`) `Mcp-Name` headers that match the body. | `server/discover`, `tools/list`, `tools/call`, `ping` |
| **2025-03-26 / 2025-11-25** | `initialize` then `notifications/initialized` | Same tools, plus empty `resources/list` / `prompts/list` |

Header mismatches return JSON-RPC error `-32020`. Notifications (`notifications/initialized`) return HTTP `202` with an empty body.

`tools/call` results use spec content (`type: text`) plus `structuredContent` for the JSON payload. The legacy REST envelope (`type: json`) is unchanged.

## Auth

Any of:

- `Authorization: Bearer <N20_MCP_DM_TOKEN>`
- `X-MCP-Token: <N20_MCP_DM_TOKEN>`
- Logged-in DM session cookie (`dm` in `user_role()`)

If an `Origin` header is present, it must match `CORS_ORIGINS` / the webapp CORS allowlist (DNS-rebinding protection). Desktop MCP clients typically omit `Origin` and are allowed.

## Legacy REST (in-app LLM)

Kept for the webapp LLM function-call bridge:

```
GET  /mcp/manifest
GET  /mcp/tools/list
POST /mcp/tools/call     {"name": "...", "arguments": {...}}
```

Same auth as above. Response envelope: `{"isError": bool, "content": [...]}`.

## Tool catalogue

See [AGENTS.md](../AGENTS.md) (keep that list in sync with `webapp/mcp/tools_*.py`). Summary:

| Module | Tools |
|---|---|
| `tools_world` | `world.list_maps` (includes `map_set` / `active`), `world.get_map`, `world.list_entities`, `world.get_entity`, `world.get_battle`, `world.list_npc_types`, `world.list_object_types` |
| `tools_dm` | HP, status, inventory, resources, spawn/teleport, battle admin, rest, save/load, audio, time, landmarks, **3D illumination** (`dm.illumination` op=`get\|set\|reset`), **DM notes** (`dm.note` op=`list\|upsert\|delete\|move`), **notebook** (`dm.notebook` op=`list\|get\|search\|create\|update\|delete\|mkdir\|move\|share`), users, **map sets** (`dm.map_set`), **sidekicks** (`dm.sidekick` op=`join\|leave\|assign_owner\|list`) |
| `tools_actions` | `actions.list_available`, `actions.execute` (optional `opts.knock_unconscious` for melee knockout), `actions.move`, `actions.end_turn`, `actions.start_battle`, `actions.end_battle` |
| `tools_npc` | `npc.get_location`, `npc.query_area` |

## Implementation

| File | Role |
|---|---|
| `n20-webapp/webapp/mcp/protocol.py` | JSON-RPC dispatcher |
| `n20-webapp/webapp/mcp/routes.py` | Flask `POST /mcp` + legacy REST |
| `n20-webapp/webapp/mcp/stdio.py` | `python -m webapp.mcp.stdio` proxy |
| `n20-webapp/webapp/mcp/tools_*.py` | DM tool handlers |
| `n20-webapp/tests/webapp/test_mcp_protocol.py` | Protocol, auth, stdio tests |

The official MCP Python SDK is **not** mounted into Flask (the production server is Flask-SocketIO + eventlet). The adapter implements the stateless 2026-07-28 POST contract directly.

## Not in this surface

- OAuth / Client ID Metadata Documents
- MCP resources, prompts, elicitation, Tasks
- Campaign YAML edit-mode (`/edit/*`)
