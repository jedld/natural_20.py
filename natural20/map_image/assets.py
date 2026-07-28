"""Resolve campaign and bundled image assets for map rendering."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image


def repo_root() -> Path:
    import natural20 as n20

    return Path(n20.__file__).resolve().parent.parent


def bundled_assets_root() -> Path:
    return repo_root() / "webapp" / "static" / "assets"


def resolve_asset_path(
    name: str,
    *,
    campaign_root: Path | None = None,
    subdir: str = "",
) -> Path | None:
    """Search campaign assets then bundled static assets."""
    filename = Path(name).name
    search: list[Path] = []
    if campaign_root is not None:
        campaign = campaign_root.resolve()
        if subdir:
            search.extend(
                [
                    campaign / "assets" / subdir / filename,
                    campaign / "assets" / "maps" / filename,
                ]
            )
        search.extend(
            [
                campaign / "assets" / filename,
                campaign / "assets" / "objects" / filename,
            ]
        )

    bundled = bundled_assets_root()
    if subdir:
        search.append(bundled / subdir / filename)
    search.extend(
        [
            bundled / filename,
            bundled / "objects" / filename,
            bundled / "editor" / filename,
        ]
    )

    for path in search:
        if path.is_file():
            return path.resolve()
    return None


@lru_cache(maxsize=256)
def load_image_cached(path: str) -> Image.Image | None:
    candidate = Path(path)
    if not candidate.is_file():
        return None
    image = Image.open(candidate)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image


def load_token_image(
    token_image: str,
    *,
    campaign_root: Path | None = None,
    tile_size: int,
) -> Image.Image | None:
    """Load and scale a token/object sprite."""
    if not token_image:
        return None
    if token_image.startswith("objects/"):
        rel = token_image.split("/", 1)[1]
        path = resolve_asset_path(rel, campaign_root=campaign_root, subdir="objects")
    else:
        path = resolve_asset_path(token_image, campaign_root=campaign_root)
    if path is None:
        return None
    image = load_image_cached(str(path))
    if image is None:
        return None
    if image.width != tile_size or image.height != tile_size:
        return image.resize((tile_size, tile_size), Image.Resampling.LANCZOS)
    return image
