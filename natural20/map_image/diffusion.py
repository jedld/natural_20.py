"""Optional diffusion backends for map background generation."""

from __future__ import annotations

import base64
import io
import os
from typing import Any

from PIL import Image

THEME_STYLE_HINTS: dict[str, str] = {
    "cathedral": "gothic cathedral nave, violet stone, stained glass light, gold accents",
    "sewer": "filthy sewer tunnels, green slime, wet bricks, murky water channels",
    "prison": "cold iron-grey prison blocks, barred corridors, oppressive lighting",
    "manor": "wealthy manor interiors, warm wood parquet, candlelit noir study",
    "street": "rainy gaslit cobblestone streets, wet reflections, urban noir",
    "tavern": "cozy tavern floorboards, warm firelight, honey oak wood",
    "docks": "wet dock planks, dark river water, misty warehouse pier",
    "cobble": "dusty market cobbles, sandy bricks",
    "dirt": "packed cave dirt and rough rock",
    "grass": "meadow grass and garden paths",
    "stone": "classic dungeon grey stone",
}


def build_map_prompt(
    name: str,
    description: str,
    *,
    style: str = "fantasy battlemap",
    palette: str | None = None,
) -> str:
    parts = [
        f"Top-down {style} underlay texture for a VTT map, seamless-feeling, no grid lines, no text, no tokens, no characters."
    ]
    if palette and palette in THEME_STYLE_HINTS:
        parts.append(f"Theme: {THEME_STYLE_HINTS[palette]}.")
    if name:
        parts.append(f"Location: {name}.")
    if description:
        parts.append(description.strip())
    parts.append("Dark atmospheric lighting, painterly, readable from above, strong local color.")
    return " ".join(parts)


def generate_background(
    prompt: str,
    width: int,
    height: int,
    *,
    provider: str = "openai",
    mcp_url: str | None = None,
    quality: str = "medium",
) -> Image.Image | None:
    provider = (provider or "openai").lower()
    if provider == "openai":
        return _generate_openai(prompt, width, height)
    if provider in {"http", "stability", "sd"}:
        return _generate_http(prompt, width, height)
    if provider in {"mcp", "image-gen", "image_gen"}:
        return _generate_mcp(prompt, width, height, mcp_url=mcp_url, quality=quality)
    raise ValueError(f"Unknown diffusion provider: {provider}")


def _generate_mcp(
    prompt: str,
    width: int,
    height: int,
    *,
    mcp_url: str | None = None,
    quality: str = "medium",
) -> Image.Image | None:
    from natural20.image_gen.mcp_client import ImageGenMcpClient, ImageGenMcpError

    # FLUX-friendly discrete sizes; resize afterward.
    if width >= height * 1.3:
        size = "1280x720"
    elif height >= width * 1.3:
        size = "720x1280"
    else:
        size = "1024x1024"
    try:
        with ImageGenMcpClient(mcp_url) as client:
            result = client.generate_image(
                prompt=prompt,
                size=size,
                quality=quality,
                negative_prompt=(
                    "text, watermark, logo, UI, characters, creatures, tokens, grid overlay, "
                    "readable letters, modern city, cars"
                ),
                output_format="png",
            )
    except ImageGenMcpError:
        return None
    image = result.image.convert("RGBA")
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return image


def _generate_openai(prompt: str, width: int, height: int) -> Image.Image | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=api_key)
    size = _nearest_dalle_size(width, height)
    response = client.images.generate(
        model=os.getenv("N20_MAP_IMAGE_MODEL", "dall-e-3"),
        prompt=prompt,
        size=size,
        quality=os.getenv("N20_MAP_IMAGE_QUALITY", "standard"),
        n=1,
        response_format="b64_json",
    )
    payload = response.data[0].b64_json
    if not payload:
        return None
    raw = base64.b64decode(payload)
    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _generate_http(prompt: str, width: int, height: int) -> Image.Image | None:
    import requests

    url = os.getenv("N20_DIFFUSION_URL")
    if not url:
        return None
    payload: dict[str, Any] = {
        "prompt": prompt,
        "width": width,
        "height": height,
    }
    headers = {}
    token = os.getenv("N20_DIFFUSION_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.post(url, json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        data = response.json()
        if "image" in data:
            raw = base64.b64decode(data["image"])
            return Image.open(io.BytesIO(raw)).convert("RGBA")
        if "url" in data:
            image_response = requests.get(data["url"], timeout=60)
            image_response.raise_for_status()
            return Image.open(io.BytesIO(image_response.content)).convert("RGBA")
        return None
    return Image.open(io.BytesIO(response.content)).convert("RGBA")


def _nearest_dalle_size(width: int, height: int) -> str:
    if width == height:
        return "1024x1024"
    if width > height:
        return "1792x1024"
    return "1024x1792"
