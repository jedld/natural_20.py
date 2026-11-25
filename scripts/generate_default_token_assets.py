#!/usr/bin/env python3
"""Generate missing default-template NPC token images via a local image-gen MCP server.

Usage: python scripts/generate_default_token_assets.py [slug ...]
Regenerates the 15 default-template tokens this script was introduced for
(SRD NPC icons + the generic PC fallback) into templates/assets/, styled to
match the bundled goblin-ambush token set (circular tan ring, cream
background, painterly bust). Drives a local image-gen MCP server
(image-gen-mcp compatible, generate_image tool); point MCP_URL below at it
(default http://0.0.0.0:8020/mcp). Requires the image-gen MCP running and
Pillow. Files are saved as 256x256 RGBA PNGs.
"""
import base64
import io
import json
import sys
import urllib.request

from PIL import Image

MCP_URL = "http://0.0.0.0:8020/mcp"

STYLE = (
    "painterly semi-realistic fantasy tabletop RPG token illustration, "
    "bust centered inside a circle with a thin tan ring border, "
    "soft off-white background, muted earthy palette, dark clean outlines, "
    "no text, no letters"
)

TOKENS = {
    # slug -> subject description
    "token_acolyte": "a young human acolyte priest in simple brown and cream temple robes wearing a brass holy symbol",
    "token_animated_armor": "an animated empty suit of late-medieval steel plate armor with a faint spectral blue glow inside the visor",
    "token_boar": "a fierce wild brown boar with tusks in three-quarter view",
    "token_commoner": "a plain human commoner peasant in a homespun beige tunic, friendly weathered face",
    "token_giantrat": "a giant gray-brown rat the size of a dog, snarling, matted fur, small fierce eyes",
    "token_gladiator": "a muscular human gladiator in bronze cuirass and red plumed helmet holding a short sword",
    "token_guard": "a stern human town guard in steel chainmail hauberk and kettle helmet holding a spear",
    "token_noble": "an elegant human nobleman in a fine dark green velvet doublet with gold embroidery",
    "token_skeleton": "an undead warrior skeleton with a battle-worn rusty helm and a cracked bone skull staring forward",
    "token_spy": "a hooded human spy in a dark cloak with the face half-shadowed, holding a dagger",
    "token_swarm_of_centipedes": "a churning swarm of giant reddish-brown centipedes with many pale legs",
    "token_vampire_spawn": "a pale fanged vampire spawn with slicked black hair and a tattered bat-wing cloak, glowing red eyes",
    "token_veteran": "a scarred grizzled human soldier veteran in dented weathered plate armor with a sword over the shoulder",
    "token_zombie": "a shambling green-skinned zombie in tattered rags with sunken eyes and slack jaw",
    "token_player": "a generic fantasy adventurer hero, a hooded half-elf ranger with leather armor and a bow strap, welcoming neutral expression",
}

# All slugs (including the generic PC fallback token) go to templates/assets/.
# Do NOT overwrite n20-webapp/webapp/static/assets/token_player.png: that is a
# tracked upstream fallback served by /assets/* for campaigns without one.
DEFAULT_TARGET = "templates/assets/{slug}.png"


def sse_data(payload: bytes) -> dict:
    """Extract the JSON-RPC message from an SSE or plain JSON body."""
    text = payload.decode("utf-8", "replace")
    if text.startswith("event:") or "\ndata:" in text or text.startswith("data:"):
        for line in text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    return json.loads(text)


class Mcp:
    def __init__(self):
        self.session_id = None

    def post(self, message, expect_response=True):
        req = urllib.request.Request(
            MCP_URL,
            data=json.dumps(message).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **({"mcp-session-id": self.session_id} if self.session_id else {}),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            sid = resp.headers.get("mcp-session-id")
            if sid:
                self.session_id = sid
            body = resp.read()
        if not expect_response or not body:
            return None
        return sse_data(body)

    def initialize(self):
        out = self.post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18",
                       "clientInfo": {"name": "n20-token-gen", "version": "1.0"},
                       "capabilities": {}},
        })
        if "error" in out:
            raise SystemExit(f"initialize failed: {out['error']}")
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"},
                  expect_response=False)

    def generate(self, prompt, slug):
        out = self.post({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "generate_image", "arguments": {
                "prompt": prompt,
                "size": "1024x1024",
                "quality": "high",
                "output_format": "png",
            }},
        })
        if "error" in out:
            raise RuntimeError(f"call error: {out['error']}")
        result = out["result"]
        if result.get("isError"):
            raise RuntimeError(f"tool error: {result['content']}")
        for part in result.get("content", []):
            if part.get("type") == "image" and part.get("data"):
                return base64.b64decode(part["data"])
        raise RuntimeError("no image content in result")


def save_png(raw: bytes, path: str, size=(256, 256)):
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    im = im.resize(size, Image.LANCZOS)
    im.save(path, "PNG")


def main():
    slugs = sys.argv[1:] or list(TOKENS)
    mcp = Mcp()
    mcp.initialize()
    failed = []
    for slug in slugs:
        subject = TOKENS[slug]
        target = DEFAULT_TARGET.format(slug=slug)
        prompt = f"portrait token of {subject}, {STYLE}"
        print(f"generating {slug} ...", flush=True)
        try:
            raw = mcp.generate(prompt, slug)
            save_png(raw, target)
            print(f"  -> {target}", flush=True)
        except Exception as exc:
            print(f"  !! {slug} failed: {exc}", flush=True)
            failed.append(slug)
    if failed:
        print("FAILED:", " ".join(failed))
        sys.exit(1)
    print("all done")


if __name__ == "__main__":
    main()
