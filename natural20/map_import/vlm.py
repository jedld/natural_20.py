"""Vision-language and text LLM clients for battlemap import.

Providers: ollama, openai, anthropic, mock, heuristic.
Image payloads are PNG base64. Text-only calls omit the image.
"""

from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from PIL import Image

from natural20.map_import.json_util import parse_json_object
from natural20.map_import.knobs import ImportKnobs
from natural20.map_import.taxonomy import OBJECT_SUBTYPES, TILE_CLASSES


TILE_SYSTEM_PROMPT = """You classify one square of a top-down D&D battlemap.
Return JSON only, no markdown, with this schema:
{
  "class": "wall|floor|void|water|door|object|unknown",
  "subtype": "none|wooden_door|chest|barrel|table|chair|bed|bookshelf|statue|column|fireplace|campfire|brazier|tree|pit|chasm|window|stairs|switch|note|altar|other",
  "orientation": "none|horizontal|vertical",
  "confidence": 0.0,
  "description": "one short sentence of what is visible in the CENTER square",
  "walls": {"N": false, "E": false, "S": false, "W": false},
  "doors": {"N": false, "E": false, "S": false, "W": false},
  "solid_wall": false
}

Rules:
- Published floorplans often draw walls as a thin ink line on the EDGE of a square
  while the rest of the cell is floor texture. That CENTER cell is still class=wall
  (or door). Do not label it floor just because most of the square is walkable art.
- walls.N true if a wall line runs along the top edge of the CENTER tile; E=right, S=bottom, W=left.
- doors.* true if that same edge is a doorway (gap in the wall, door leaf, or arch).
- solid_wall true only if the whole square is filled masonry/stone, not a thin outline.
- class=void: art outside the playable map (black/empty margins).
- class=water: pool, river, moat.
- class=object: furniture or props in the interior of the square. Set subtype to the best match.
- The red outline (if present) marks the CENTER tile you must classify. Ignore neighbors except as context.
- Prefer the Ink edges prior when the center looks like floor with a dark border.
- Printed cartography is NOT a wall: titles ("Ground Floor", "Basement", "Church"),
  compass roses, scale bars ("One square = 5 feet"), and circled room keys (a, b, c).
  Classify the terrain UNDER that ink. Do not set walls/doors from letter strokes.
- Do not invent creatures; NPCs are placed later from the adventure text.
"""


def image_to_png_b64(image: Image.Image, *, max_side: int = 384) -> str:
    img = image.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


class VlmClient(ABC):
    name: str = "base"

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        image: Image.Image | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        raise NotImplementedError

    def classify_json(self, prompt: str, *, image: Image.Image | None = None) -> dict[str, Any]:
        text = self.complete(prompt, image=image, system=TILE_SYSTEM_PROMPT, max_tokens=400)
        try:
            data = parse_json_object(text)
        except (ValueError, json.JSONDecodeError):
            data = {
                "class": "unknown",
                "subtype": "none",
                "orientation": "none",
                "confidence": 0.2,
                "description": text[:240],
            }
        data["_raw"] = text
        return data


class HeuristicClient(VlmClient):
    """No network: echo CV prior already embedded in the prompt."""

    name = "heuristic"

    def complete(
        self,
        prompt: str,
        *,
        image: Image.Image | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        # classify.py already filled the record from features; this is a stub.
        return json.dumps(
            {
                "class": "unknown",
                "subtype": "none",
                "orientation": "none",
                "confidence": 0.0,
                "description": "heuristic client does not call a model",
            }
        )


class MockClient(VlmClient):
    """Deterministic VLM stand-in: uses the heuristic line in the prompt if present."""

    name = "mock"

    def complete(
        self,
        prompt: str,
        *,
        image: Image.Image | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if "Place only features the text actually describes" in (system or "") or prompt.startswith("ASCII map:"):
            return json.dumps(
                {
                    "spawn": [2, 2],
                    "npcs": [],
                    "objects": [],
                    "notes": [],
                    "annotations": [
                        {
                            "id": "main_room",
                            "label": "Main room",
                            "description": "Imported interior.",
                            "kind": "area",
                            "bounds": {"x1": 1, "y1": 1, "x2": 3, "y2": 3},
                        }
                    ],
                    "fixes": [],
                    "unplaced": [],
                }
            )
        if "last quality pass" in (system or "") or prompt.startswith("ASCII:"):
            return json.dumps(
                {
                    "tile_fixes": [],
                    "remove_entities_at": [],
                    "add_entities": [],
                    "add_annotations": [],
                    "summary": "mock refine: no changes",
                }
            )
        if "verify EVERY listed square" in (system or "") or "verify each listed square" in (system or "").lower():
            return json.dumps({"fixes": [], "notes": ["mock region verify: no changes"]})
        if "You review a Natural20 battlemap transcribed tile-by-tile" in (system or ""):
            return json.dumps({"fixes": [], "notes": ["mock consistency: no changes"]})
        if "several floor plans" in (system or "") or "published D&D adventure map PAGE" in (system or ""):
            return json.dumps(
                {
                    "page_title": "Imported page",
                    "panels": [
                        {
                            "id": "left",
                            "label": "Ground Floor",
                            "kind": "battlemap",
                            "bounds": {"x1": 0.0, "y1": 0.0, "x2": 0.5, "y2": 1.0},
                        },
                        {
                            "id": "right",
                            "label": "Upper Level",
                            "kind": "battlemap",
                            "bounds": {"x1": 0.5, "y1": 0.0, "x2": 1.0, "y2": 1.0},
                        },
                    ],
                }
            )
        heuristic_class = "floor"
        subtype = "none"
        confidence = 0.7
        walls = {"N": False, "E": False, "S": False, "W": False}
        doors = {"N": False, "E": False, "S": False, "W": False}
        for line in prompt.splitlines():
            if line.startswith("Heuristic prior:"):
                parts = line.split()
                if len(parts) >= 3:
                    label = parts[2]
                    if "/" in label:
                        heuristic_class, subtype = label.split("/", 1)
                    else:
                        heuristic_class = label
                for part in parts:
                    if part.startswith("confidence="):
                        try:
                            confidence = float(part.split("=", 1)[1])
                        except ValueError:
                            pass
            if line.startswith("Ink edges:"):
                walls, doors = _parse_ink_edge_line(line)
        if heuristic_class not in TILE_CLASSES:
            heuristic_class = "floor"
        if subtype not in OBJECT_SUBTYPES:
            subtype = "none"
        orientation = "none"
        if heuristic_class == "door":
            orientation = "horizontal"
            if doors.get("E") or doors.get("W") or ("N=wall" in prompt and "S=wall" in prompt):
                orientation = "vertical"
            elif doors.get("N") or doors.get("S") or ("E=wall" in prompt and "W=wall" in prompt):
                orientation = "horizontal"
        return json.dumps(
            {
                "class": heuristic_class,
                "subtype": subtype,
                "orientation": orientation,
                "confidence": min(0.95, confidence + 0.1),
                "description": f"mock classified {heuristic_class}/{subtype}",
                "walls": walls,
                "doors": doors,
            }
        )


class OllamaClient(VlmClient):
    name = "ollama"

    def __init__(self, *, model: str, base_url: str, timeout: int = 90) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        prompt: str,
        *,
        image: Image.Image | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        message: dict[str, Any] = {"role": "user", "content": prompt}
        if image is not None:
            message["images"] = [image_to_png_b64(image)]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": int(max_tokens or 400)},
        }
        if system:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append(message)
        return _http_json_post(f"{self.base_url}/api/chat", payload, timeout=self.timeout).get(
            "message", {}
        ).get("content", "")


class OpenAIClient(VlmClient):
    name = "openai"

    def __init__(self, *, model: str, api_key: str, timeout: int = 90, base_url: str | None = None) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def complete(
        self,
        prompt: str,
        *,
        image: Image.Image | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        user_content: Any
        if image is not None:
            user_content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_to_png_b64(image)}"},
                },
            ]
        else:
            user_content = prompt
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_content})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": int(max_tokens or 800),
        }
        data = _http_json_post(
            f"{self.base_url}/chat/completions",
            payload,
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return data.get("choices", [{}])[0].get("message", {}).get("content") or ""


class AnthropicClient(VlmClient):
    name = "anthropic"

    def __init__(self, *, model: str, api_key: str, timeout: int = 90) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(
        self,
        prompt: str,
        *,
        image: Image.Image | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        content: list[dict[str, Any]] = []
        if image is not None:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_to_png_b64(image),
                    },
                }
            )
        content.append({"type": "text", "text": prompt})
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": int(max_tokens or 800),
            "temperature": 0.1,
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            payload["system"] = system
        data = _http_json_post(
            "https://api.anthropic.com/v1/messages",
            payload,
            timeout=self.timeout,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        parts = data.get("content") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        return "".join(texts)


def _http_json_post(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"VLM HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"VLM request failed for {url}: {exc}") from exc


def _parse_ink_edge_line(line: str) -> tuple[dict[str, bool], dict[str, bool]]:
    walls = {"N": False, "E": False, "S": False, "W": False}
    doors = {"N": False, "E": False, "S": False, "W": False}
    # "Ink edges: walls=NS doors=S scores=..." or "walls=- doors=-"
    body = line.split(":", 1)[1] if ":" in line else line
    for token in body.replace(",", " ").split():
        if token.startswith("walls="):
            for side in token.split("=", 1)[1]:
                if side in walls:
                    walls[side] = True
        elif token.startswith("doors="):
            for side in token.split("=", 1)[1]:
                if side in doors:
                    doors[side] = True
                    walls[side] = True
    return walls, doors


def build_client(knobs: ImportKnobs) -> VlmClient:
    provider = (knobs.provider or "heuristic").lower()
    if knobs.skip_vlm:
        provider = "heuristic"
    timeout = int(knobs.timeout or 90)
    if provider == "heuristic":
        return HeuristicClient()
    if provider == "mock":
        return MockClient()
    if provider == "ollama":
        model = knobs.model or _env("MAP_IMPORT_VLM_MODEL") or _env("OLLAMA_MODEL") or "llava"
        base = knobs.base_url or _env("MAP_IMPORT_VLM_BASE_URL") or _env("OLLAMA_BASE_URL") or "http://localhost:11434"
        return OllamaClient(model=model, base_url=base, timeout=timeout)
    if provider == "openai":
        model = knobs.model or _env("MAP_IMPORT_VLM_MODEL") or _env("OPENAI_MODEL") or "gpt-4o-mini"
        key = knobs.api_key or _env("MAP_IMPORT_VLM_API_KEY") or _env("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OpenAI VLM requires OPENAI_API_KEY or --api-key")
        base = knobs.base_url or _env("OPENAI_BASE_URL")
        return OpenAIClient(model=model, api_key=key, timeout=timeout, base_url=base)
    if provider == "anthropic":
        model = knobs.model or _env("MAP_IMPORT_VLM_MODEL") or _env("ANTHROPIC_MODEL") or "claude-sonnet-4-5"
        key = knobs.api_key or _env("MAP_IMPORT_VLM_API_KEY") or _env("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("Anthropic VLM requires ANTHROPIC_API_KEY or --api-key")
        return AnthropicClient(model=model, api_key=key, timeout=timeout)
    raise ValueError(f"Unknown VLM provider: {provider}")
