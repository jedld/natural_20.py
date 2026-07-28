"""In-place PNG/WebP optimization for small UI icons."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except OSError:
        return False


def _downscale_if_needed(img: Image.Image, max_dim: int) -> Image.Image:
    if max_dim <= 0:
        return img
    width, height = img.size
    if max(width, height) <= max_dim:
        return img
    scale = max_dim / float(max(width, height))
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _optimize_png_file(src: Path, dst: Path, *, max_dim: int) -> None:
    with Image.open(src) as image:
        image.load()
        if image.mode not in ("P", "RGB", "RGBA", "LA", "L"):
            image = image.convert("RGBA")
        image = _downscale_if_needed(image, max_dim)
        image.save(dst, format="PNG", optimize=True)
    if _have("optipng"):
        _run(["optipng", "-quiet", "-o4", str(dst)])


def _write_webp_companion(src: Path, *, max_dim: int, quality: int) -> Path | None:
    companion = src.with_suffix(".webp")
    if _have("cwebp"):
        ok = _run(["cwebp", "-quiet", "-q", str(quality), str(src), "-o", str(companion)])
        if not ok:
            return None
        return companion
    with Image.open(src) as image:
        image.load()
        image = _downscale_if_needed(image, max_dim)
        if image.mode == "P":
            image = image.convert("RGBA")
        image.save(companion, format="WEBP", quality=quality, method=6)
    return companion


def optimize_icon_for_web(
    path: Path | str,
    *,
    max_dim: int = 128,
    webp: bool = False,
    webp_quality: int = 82,
) -> dict[str, Any]:
    """Losslessly compress a PNG icon in place; optionally emit a .webp sibling."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(target)

    before = target.stat().st_size
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".icon_opt_",
            suffix=target.suffix.lower(),
            dir=str(target.parent),
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
        _optimize_png_file(target, tmp_path, max_dim=max_dim)
        after = tmp_path.stat().st_size
        if after <= before:
            shutil.copystat(target, tmp_path)
            os.replace(tmp_path, target)
            tmp_path = None
        png_after = target.stat().st_size
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    result: dict[str, Any] = {
        "path": str(target),
        "bytes_before": before,
        "bytes_after": png_after,
        "webp": None,
    }
    if webp:
        companion = _write_webp_companion(target, max_dim=max_dim, quality=webp_quality)
        if companion is not None and companion.is_file():
            result["webp"] = str(companion)
            result["webp_bytes"] = companion.stat().st_size
    return result
