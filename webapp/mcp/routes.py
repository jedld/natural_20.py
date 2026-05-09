"""Flask blueprint exposing the MCP tool surface over HTTP/JSON.

Three discovery endpoints are provided:

- ``GET  /mcp/manifest``       — server metadata + tool count.
- ``GET  /mcp/tools/list``     — full tool manifest (JSON Schema inputs).
- ``POST /mcp/tools/call``     — body ``{"name": str, "arguments": object}``;
  returns an MCP-style envelope ``{"isError": bool, "content": [...]}``.

Authorisation: requests must either come from a logged-in DM session
(``'dm' in user_role()``), or carry an ``X-MCP-Token`` header that
matches the ``N20_MCP_DM_TOKEN`` environment variable. If the env var
is unset, only DM session callers are accepted.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from flask import Blueprint, jsonify, request

from .context import MCPContext
from .tool_registry import ToolRegistry
from . import tools_actions, tools_dm, tools_world


def build_default_registry() -> ToolRegistry:
    """Create a registry pre-populated with all stock MCP tool modules."""
    registry = ToolRegistry()
    tools_world.register(registry)
    tools_dm.register(registry)
    tools_actions.register(registry)
    return registry


def register_mcp_blueprint(app, context: MCPContext,
                           registry: Optional[ToolRegistry] = None,
                           user_role_fn: Optional[Callable[[], object]] = None,
                           url_prefix: str = '/mcp') -> Blueprint:
    """Build, configure, and register the ``/mcp`` blueprint on ``app``.

    Returns the blueprint so the caller can introspect it for tests.
    """
    if registry is None:
        registry = build_default_registry()

    bp = Blueprint('mcp', __name__, url_prefix=url_prefix)

    def _authorised() -> bool:
        token = os.environ.get('N20_MCP_DM_TOKEN', '').strip()
        if token:
            header = request.headers.get('X-MCP-Token', '').strip()
            if header and header == token:
                return True
        if user_role_fn is not None:
            try:
                role = user_role_fn() or []
                if 'dm' in role:
                    return True
            except Exception:
                pass
        return False

    @bp.before_request
    def _gate():
        # Allow CORS-style preflight without auth.
        if request.method == 'OPTIONS':
            return None
        if not _authorised():
            return jsonify({
                'isError': True,
                'content': [{'type': 'text', 'text': 'Unauthorized'}],
            }), 401
        return None

    @bp.route('/manifest', methods=['GET'])
    def manifest():
        tools = registry.list()
        return jsonify({
            'protocol': 'mcp-tools',
            'protocolVersion': '0.1',
            'serverName': 'natural20-webapp',
            'description': ('Tool surface over the running Natural20 game; '
                            'lets a DM-acting LLM inspect, mutate and drive entities.'),
            'toolCount': len(tools),
            'categories': sorted({t['category'] for t in tools}),
        })

    @bp.route('/tools/list', methods=['GET'])
    def tools_list():
        return jsonify({'tools': registry.list()})

    @bp.route('/tools/call', methods=['POST'])
    def tools_call():
        payload = request.get_json(silent=True) or {}
        name = payload.get('name')
        arguments = payload.get('arguments') or {}
        if not name:
            return jsonify({
                'isError': True,
                'content': [{'type': 'text', 'text': 'Missing "name" in request body'}],
            }), 400
        envelope = registry.call(name, arguments, context=context)
        status = 200 if not envelope.get('isError') else 400
        return jsonify(envelope), status

    app.register_blueprint(bp)
    # Stash on the app so tests can introspect.
    app.extensions = getattr(app, 'extensions', {}) or {}
    app.extensions['mcp_registry'] = registry
    app.extensions['mcp_context'] = context
    return bp
