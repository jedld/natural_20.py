"""Minimal streamable-HTTP client for the local Image Gen MCP server."""

from __future__ import annotations

import base64
import io
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image


class ImageGenMcpError(RuntimeError):
    """Raised when the Image Gen MCP server cannot fulfill a request."""


@dataclass
class GeneratedImage:
    image: Image.Image
    summary: str = ""
    raw_content: list[dict[str, Any]] | None = None


def default_mcp_url() -> str:
    return (
        os.getenv("N20_IMAGE_GEN_MCP_URL")
        or os.getenv("IMAGE_GEN_MCP_URL")
        or "http://127.0.0.1:8020/mcp"
    )


class ImageGenMcpClient:
    """JSON-RPC client for ``Image Gen MCP (local)`` over streamable HTTP."""

    def __init__(
        self,
        url: str | None = None,
        *,
        timeout: float = 600.0,
        client_name: str = "natural20-image-gen",
        client_version: str = "0.1",
    ) -> None:
        self.url = (url or default_mcp_url()).rstrip("/")
        self.timeout = timeout
        self.client_name = client_name
        self.client_version = client_version
        self._session_id: str | None = None
        self._request_id = 0

    def __enter__(self) -> "ImageGenMcpClient":
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._session_id = None

    def initialize(self) -> dict[str, Any]:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": self.client_name,
                    "version": self.client_version,
                },
            },
            require_session=False,
        )
        self._notify("notifications/initialized")
        return result

    def check_server_status(self) -> dict[str, Any]:
        return self.call_tool("check_server_status", {})

    def list_available_models(self) -> dict[str, Any]:
        return self.call_tool("list_available_models", {})

    def generate_image(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
        aspect_ratio: str | None = None,
        quality: str = "medium",
        output_format: str = "png",
        negative_prompt: str | None = None,
        model: str | None = None,
        seed: int = -1,
        guidance_scale: float | None = None,
        num_inference_steps: int | None = None,
    ) -> GeneratedImage:
        args: dict[str, Any] = {
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "output_format": output_format,
            "seed": seed,
        }
        if aspect_ratio:
            args["aspect_ratio"] = aspect_ratio
        if negative_prompt:
            args["negative_prompt"] = negative_prompt
        if model:
            args["model"] = model
        if guidance_scale is not None:
            args["guidance_scale"] = guidance_scale
        if num_inference_steps is not None:
            args["num_inference_steps"] = num_inference_steps

        payload = self.call_tool("generate_image", args)
        if payload.get("isError"):
            raise ImageGenMcpError(self._content_text(payload) or "generate_image failed")
        image = self._image_from_content(payload.get("content") or [])
        if image is None:
            raise ImageGenMcpError("generate_image returned no image content")
        return GeneratedImage(
            image=image,
            summary=self._content_text(payload) or "",
            raw_content=payload.get("content"),
        )

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._session_id is None:
            self.initialize()
        return self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )

    # --- transport --------------------------------------------------------- #

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        require_session: bool = True,
    ) -> dict[str, Any]:
        if require_session and self._session_id is None:
            raise ImageGenMcpError("MCP session not initialized")
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        raw, response_headers = self._post(body, headers)
        session = response_headers.get("mcp-session-id") or response_headers.get("Mcp-Session-Id")
        if session:
            self._session_id = session
        message = self._parse_sse_or_json(raw)
        if "error" in message:
            err = message["error"]
            raise ImageGenMcpError(f"MCP {method} error: {err}")
        result = message.get("result")
        if not isinstance(result, dict):
            raise ImageGenMcpError(f"MCP {method} returned unexpected result: {message!r}")
        return result

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            self._post(body, headers)
        except ImageGenMcpError:
            # Some servers return empty body on notifications; ignore soft failures.
            pass

    def _post(self, body: dict[str, Any], headers: dict[str, str]) -> tuple[str, dict[str, str]]:
        data = json.dumps(body).encode("utf-8")
        request = Request(self.url, data=data, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                response_headers = {k.lower(): v for k, v in response.headers.items()}
                return raw, response_headers
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ImageGenMcpError(f"HTTP {exc.code} from {self.url}: {detail[:500]}") from exc
        except URLError as exc:
            raise ImageGenMcpError(f"Cannot reach Image Gen MCP at {self.url}: {exc}") from exc

    @staticmethod
    def _parse_sse_or_json(raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if not text:
            return {}
        if text.startswith("{"):
            return json.loads(text)
        # SSE: take the last JSON `data:` payload (ignore ping comments).
        payload = None
        for line in text.splitlines():
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk:
                    payload = chunk
        if payload is None:
            raise ImageGenMcpError(f"Unparseable MCP response: {text[:300]!r}")
        return json.loads(payload)

    @staticmethod
    def _content_text(payload: dict[str, Any]) -> str:
        parts = []
        for item in payload.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()

    @staticmethod
    def _image_from_content(content: list[Any]) -> Image.Image | None:
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "image":
                continue
            data = item.get("data") or item.get("blob")
            if not data and item.get("source"):
                source = item["source"]
                if isinstance(source, dict):
                    data = source.get("data")
            if not data:
                continue
            if isinstance(data, str) and data.startswith("data:"):
                # data:image/png;base64,...
                data = data.split(",", 1)[-1]
            raw = base64.b64decode(data)
            return Image.open(io.BytesIO(raw)).convert("RGBA")
        # Some servers nest image bytes inside text JSON — ignore.
        return None


def save_pil(image: Image.Image, path: str | os.PathLike[str], *, format: str | None = None) -> None:
    path = str(path)
    fmt = format
    if fmt is None:
        lower = path.lower()
        if lower.endswith((".jpg", ".jpeg")):
            fmt = "JPEG"
        elif lower.endswith(".webp"):
            fmt = "WEBP"
        else:
            fmt = "PNG"
    out = image
    if fmt.upper() in {"JPEG", "JPG"} and out.mode == "RGBA":
        background = Image.new("RGB", out.size, (12, 10, 14))
        background.paste(out, mask=out.split()[-1])
        out = background
    elif fmt.upper() == "JPEG" and out.mode != "RGB":
        out = out.convert("RGB")
    out.save(path, format=fmt)


def unique_seed() -> int:
    return uuid.uuid4().int % (2**31 - 1)
