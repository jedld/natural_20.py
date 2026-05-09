"""MCP (Model Context Protocol) surface for the running game.

This package exposes a tool-oriented HTTP/JSON surface that lets an LLM
acting as a Dungeon Master inspect, mutate, create, and act on entities
inside the currently running webapp game. The surface is organised into
logical modules:

- :mod:`webapp.mcp.tools_world` — read-only inspection (maps, entities,
  battle state).
- :mod:`webapp.mcp.tools_dm` — direct DM mutations (HP, statuses,
  properties, spawn/remove/teleport).
- :mod:`webapp.mcp.tools_actions` — turn-based execution (MoveAction,
  attack, spell, generic action dispatch, end_turn, start/end battle).

All tools are registered into a shared :class:`ToolRegistry`. The Flask
blueprint in :mod:`webapp.mcp.routes` exposes the registry under the
``/mcp/*`` URL prefix and provides three discovery endpoints
(`/mcp/manifest`, `/mcp/tools/list`, `/mcp/tools/call`) that mirror the
Anthropic / Model Context Protocol "tools" envelope so a thin MCP server
bridge can wrap them.
"""

from .context import MCPContext
from .tool_registry import Tool, ToolRegistry, tool
from .routes import register_mcp_blueprint, build_default_registry

__all__ = [
    'MCPContext',
    'Tool',
    'ToolRegistry',
    'tool',
    'register_mcp_blueprint',
    'build_default_registry',
]
