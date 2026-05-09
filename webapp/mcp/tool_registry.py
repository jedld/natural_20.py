"""A tiny tool registry modeled on the MCP "tools" surface.

A :class:`Tool` wraps a Python callable together with the JSON-schema
fragment that describes its inputs. The registry is responsible for
dispatching ``tools/call`` requests to the correct callable, validating
required arguments and translating exceptions into JSON-serialisable
error envelopes that match the MCP wire format
(``{"isError": True, "content": [...]}``).
"""

from __future__ import annotations

import inspect
import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    category: str = 'misc'

    def manifest(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'inputSchema': self.input_schema or {'type': 'object', 'properties': {}},
            'category': self.category,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f'Tool already registered: {tool.name}')
        self._tools[tool.name] = tool
        return tool

    def list(self) -> List[Dict[str, Any]]:
        return [t.manifest() for t in sorted(self._tools.values(), key=lambda t: t.name)]

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def call(self, name: str, arguments: Optional[Dict[str, Any]] = None,
             context: Any = None) -> Dict[str, Any]:
        """Invoke a tool by name. Returns an MCP-style envelope.

        On success: ``{"content": [{"type": "json", "json": <result>}],
        "isError": False}``. On failure: ``{"content": [{"type": "text",
        "text": <message>}], "isError": True}``.
        """
        tool = self._tools.get(name)
        if tool is None:
            return _error_envelope(f'Unknown tool: {name}')

        arguments = dict(arguments or {})
        # Inject the context as first kwarg if the handler accepts it.
        sig = inspect.signature(tool.handler)
        kwargs = {}
        for pname, param in sig.parameters.items():
            if pname == 'context':
                kwargs['context'] = context
                continue
            if pname in arguments:
                kwargs[pname] = arguments[pname]
            elif param.default is inspect.Parameter.empty:
                return _error_envelope(
                    f"Missing required argument '{pname}' for tool '{name}'"
                )

        try:
            result = tool.handler(**kwargs)
        except _ToolError as exc:
            return _error_envelope(str(exc))
        except Exception as exc:  # noqa: BLE001 - surface as JSON error
            logger.exception('MCP tool %s raised', name)
            return _error_envelope(f'{exc.__class__.__name__}: {exc}',
                                   traceback=traceback.format_exc())

        return {
            'isError': False,
            'content': [{'type': 'json', 'json': result}],
        }


def tool(registry: ToolRegistry, name: str, description: str,
         input_schema: Optional[Dict[str, Any]] = None,
         category: str = 'misc'):
    """Decorator: register the wrapped callable as an MCP tool."""

    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        registry.register(Tool(
            name=name,
            description=description,
            handler=fn,
            input_schema=input_schema or {'type': 'object', 'properties': {}},
            category=category,
        ))
        return fn

    return _wrap


class _ToolError(Exception):
    """Raised inside tool handlers to surface a clean error message."""


def tool_error(message: str) -> _ToolError:
    return _ToolError(message)


def _error_envelope(message: str, traceback: Optional[str] = None) -> Dict[str, Any]:
    content: List[Dict[str, Any]] = [{'type': 'text', 'text': message}]
    if traceback:
        content.append({'type': 'text', 'text': traceback})
    return {'isError': True, 'content': content}
