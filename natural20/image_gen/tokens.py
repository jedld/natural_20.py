"""Circular VTT token post-processing (shared with character creation)."""

from __future__ import annotations

from typing import Sequence

from PIL import Image, ImageDraw

# Matches webapp character-builder ring (brown leather / wood tone).
DEFAULT_RING_COLOR = (74, 47, 25, 255)
DEFAULT_TOKEN_SIZE = 256
DEFAULT_RING_WIDTH = 4

# Vertical center of the face region for tall portrait art (fraction of image height).
PORTRAIT_FACE_CENTER_Y = 0.28
# Tighter square crop on portraits so the head fills most of the token.
PORTRAIT_CROP_HEIGHT_RATIO = 0.58


def crop_for_token(
    pil_img: Image.Image,
    *,
    face_center_y: float = PORTRAIT_FACE_CENTER_Y,
    portrait_height_ratio: float = PORTRAIT_CROP_HEIGHT_RATIO,
) -> Image.Image:
    """Crop to a square region with the subject's face centered for VTT tokens.

  Tall portrait art (e.g. 896x1152) is usually framed head-to-waist with the face
  in the upper third. A naive geometric center crop cuts off heads or shows too
  much body. This biases the crop toward the face and zooms slightly so the head
  occupies most of the circular token.
  """
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")

    width, height = pil_img.size
    if width <= 0 or height <= 0:
        return pil_img

    if height > width * 1.05:
        side = int(min(width, height * portrait_height_ratio))
        side = max(32, min(side, width, height))
        center_x = width // 2
        center_y = int(height * face_center_y)
        left = max(0, min(center_x - side // 2, width - side))
        top = max(0, min(center_y - side // 2, height - side))
    else:
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2

    return pil_img.crop((left, top, left + side, top + side))


def make_circular_token(
    pil_img: Image.Image,
    size: int = DEFAULT_TOKEN_SIZE,
    ring_width: int = DEFAULT_RING_WIDTH,
    ring_color: Sequence[int] = DEFAULT_RING_COLOR,
) -> Image.Image:
    """Crop and mask a PIL image into a circular token with an optional ring.

    This is the same algorithm used by the webapp character builder
    (``webapp.blueprints.helpers.character_builder_utils``).
    """
    pil_img = crop_for_token(pil_img)
    pil_img = pil_img.resize((size, size), Image.LANCZOS)

    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)

    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(pil_img, (0, 0), mask)

    if ring_width and ring_width > 0:
        draw = ImageDraw.Draw(result)
        for i in range(ring_width):
            draw.ellipse(
                (i, i, size - 1 - i, size - 1 - i),
                outline=tuple(ring_color),
            )
    return result
