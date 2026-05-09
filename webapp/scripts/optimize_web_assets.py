#!/usr/bin/env python3
"""Scan the webapp static tree for new/changed image assets and optimize them in-place.

Features
--------
- Recursively walks one or more roots (defaults to ``webapp/static``).
- Tracks previously optimized files in a JSON manifest so re-runs only touch
  new or modified assets.
- Downscales oversized images to a configurable max dimension while preserving
  aspect ratio.
- Re-encodes PNG/JPEG/WebP/GIF with lossless or near-lossless compression.
- Optionally emits a ``.webp`` companion for large raster assets (``--webp``).
- Prefers external optimizers (``optipng``, ``jpegoptim``, ``cwebp``) when
  available, falls back to Pillow.

Usage
-----
    python optimize_web_assets.py                 # scan default roots, optimize new files
    python optimize_web_assets.py --dry-run       # report what would change
    python optimize_web_assets.py --force         # re-optimize everything
    python optimize_web_assets.py --webp          # also generate .webp companions
    python optimize_web_assets.py path1 path2 ... # custom roots

Exit code is 0 unless an unrecoverable error occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image
except ImportError:  # pragma: no cover - guard for missing dep
    print("error: Pillow is required (pip install pillow)", file=sys.stderr)
    sys.exit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = (SCRIPT_DIR / ".." / "static").resolve()
DEFAULT_MANIFEST = SCRIPT_DIR / ".asset_manifest.json"

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
# Skip outputs we generated previously and any third-party libs we shouldn't touch.
SKIP_DIR_NAMES = {"libs", "node_modules", "__pycache__"}
SKIP_NAME_SUFFIXES = ("-optimized.png", "-optimized.jpg", "-optimized.jpeg")


@dataclass
class Stats:
    scanned: int = 0
    skipped: int = 0
    optimized: int = 0
    failed: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    webp_created: int = 0
    webp_bytes: int = 0
    errors: list[str] = field(default_factory=list)


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_manifest(path: Path, manifest: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    tmp.replace(path)


def iter_assets(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            print(f"warn: root not found: {root}", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".")]
            for name in filenames:
                if name.lower().endswith(SKIP_NAME_SUFFIXES):
                    continue
                ext = Path(name).suffix.lower()
                if ext in SUPPORTED_EXTS:
                    yield Path(dirpath) / name


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except OSError:
        return False


def downscale_if_needed(img: Image.Image, max_dim: int) -> tuple[Image.Image, bool]:
    if max_dim <= 0:
        return img, False
    w, h = img.size
    if max(w, h) <= max_dim:
        return img, False
    scale = max_dim / float(max(w, h))
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size, Image.LANCZOS), True


def optimize_png(src: Path, dst: Path, max_dim: int) -> None:
    with Image.open(src) as im:
        im.load()
        im, resized = downscale_if_needed(im, max_dim)
        save_kwargs = {"optimize": True}
        # Preserve palette where it makes sense; otherwise keep RGBA/RGB.
        if im.mode not in ("P", "RGB", "RGBA", "LA", "L"):
            im = im.convert("RGBA")
        im.save(dst, format="PNG", **save_kwargs)
    if have("optipng"):
        run(["optipng", "-quiet", "-o4", str(dst)])


def optimize_jpeg(src: Path, dst: Path, max_dim: int, quality: int) -> None:
    with Image.open(src) as im:
        im.load()
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im, _ = downscale_if_needed(im, max_dim)
        im.save(
            dst,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
    if have("jpegoptim"):
        run(["jpegoptim", "--strip-all", "--quiet", str(dst)])


def optimize_webp(src: Path, dst: Path, max_dim: int, quality: int) -> None:
    with Image.open(src) as im:
        im.load()
        im, _ = downscale_if_needed(im, max_dim)
        # Use lossless for images with alpha that look palette-like; otherwise quality-based.
        lossless = im.mode in ("P", "LA") or (im.mode == "RGBA" and im.size[0] * im.size[1] <= 64 * 64)
        if lossless:
            im.save(dst, format="WEBP", lossless=True, method=6)
        else:
            if im.mode == "P":
                im = im.convert("RGBA")
            im.save(dst, format="WEBP", quality=quality, method=6)


def optimize_gif(src: Path, dst: Path, max_dim: int) -> None:
    # Only resize the first frame intelligently; keep animation intact otherwise.
    with Image.open(src) as im:
        if getattr(im, "is_animated", False):
            # Animated GIFs are risky to recompress with Pillow; copy as-is.
            shutil.copy2(src, dst)
            return
        im, _ = downscale_if_needed(im, max_dim)
        im.save(dst, format="GIF", optimize=True)


def make_webp_companion(src: Path, max_dim: int, quality: int) -> tuple[Path, int] | None:
    companion = src.with_suffix(".webp")
    if companion.exists() and companion.stat().st_mtime >= src.stat().st_mtime:
        return None
    try:
        if have("cwebp"):
            ok = run(["cwebp", "-quiet", "-q", str(quality), str(src), "-o", str(companion)])
            if not ok:
                raise RuntimeError("cwebp failed")
        else:
            with Image.open(src) as im:
                im.load()
                im, _ = downscale_if_needed(im, max_dim)
                if im.mode == "P":
                    im = im.convert("RGBA")
                im.save(companion, format="WEBP", quality=quality, method=6)
        return companion, companion.stat().st_size
    except Exception as exc:  # pragma: no cover - defensive
        if companion.exists():
            try:
                companion.unlink()
            except OSError:
                pass
        raise exc


def optimize_one(path: Path, max_dim: int, quality: int, dry_run: bool) -> tuple[int, int]:
    """Return (bytes_before, bytes_after). Raises on failure."""
    ext = path.suffix.lower()
    before = path.stat().st_size

    with tempfile.NamedTemporaryFile(
        prefix=".opt_", suffix=ext, dir=str(path.parent), delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        if ext == ".png":
            optimize_png(path, tmp_path, max_dim)
        elif ext in (".jpg", ".jpeg"):
            optimize_jpeg(path, tmp_path, max_dim, quality)
        elif ext == ".webp":
            optimize_webp(path, tmp_path, max_dim, quality)
        elif ext == ".gif":
            optimize_gif(path, tmp_path, max_dim)
        else:
            raise ValueError(f"unsupported extension: {ext}")

        after = tmp_path.stat().st_size
        # Only replace if we actually saved bytes.
        if after < before and not dry_run:
            shutil.copystat(path, tmp_path)
            os.replace(tmp_path, path)
            tmp_path = None
            return before, after
        if after >= before:
            return before, before
        return before, after
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def fingerprint(path: Path) -> dict:
    st = path.stat()
    return {
        "size": st.st_size,
        "mtime": int(st.st_mtime),
        "sha1": sha1_of(path),
    }


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="*", type=Path, help="Folders to scan (default: webapp/static)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to JSON manifest tracking optimized files")
    parser.add_argument("--max-dim", type=int, default=1024, help="Downscale images whose largest side exceeds this (px). 0 disables resizing.")
    parser.add_argument("--quality", type=int, default=85, help="JPEG/WebP quality (1-100)")
    parser.add_argument("--webp", action="store_true", help="Also create .webp companions for PNG/JPEG sources")
    parser.add_argument("--webp-quality", type=int, default=82, help="Quality for generated .webp companions")
    parser.add_argument("--force", action="store_true", help="Re-optimize files even if the manifest says they're current")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without modifying files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args(argv)

    roots = [r.resolve() for r in (args.roots or [DEFAULT_ROOT])]
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path)
    stats = Stats()

    for asset in iter_assets(roots):
        stats.scanned += 1
        rel = str(asset.resolve())
        try:
            current = fingerprint(asset)
        except OSError as exc:
            stats.failed += 1
            stats.errors.append(f"{asset}: {exc}")
            continue

        prior = manifest.get(rel)
        already_done = (
            not args.force
            and prior is not None
            and prior.get("sha1") == current["sha1"]
        )
        if already_done:
            stats.skipped += 1
            if args.verbose:
                print(f"skip   {asset}")
            continue

        try:
            before, after = optimize_one(asset, args.max_dim, args.quality, args.dry_run)
        except Exception as exc:
            stats.failed += 1
            stats.errors.append(f"{asset}: {exc}")
            print(f"fail   {asset}: {exc}", file=sys.stderr)
            continue

        stats.optimized += 1
        stats.bytes_before += before
        stats.bytes_after += after
        savings = before - after
        pct = (savings / before * 100.0) if before else 0.0
        action = "would optimize" if args.dry_run else "optimized"
        print(f"{action}: {asset}  {fmt_bytes(before)} -> {fmt_bytes(after)} ({pct:.1f}% saved)")

        if args.webp and asset.suffix.lower() in (".png", ".jpg", ".jpeg") and not args.dry_run:
            try:
                result = make_webp_companion(asset, args.max_dim, args.webp_quality)
                if result is not None:
                    companion, size = result
                    stats.webp_created += 1
                    stats.webp_bytes += size
                    if args.verbose:
                        print(f"  +webp {companion} ({fmt_bytes(size)})")
            except Exception as exc:
                stats.errors.append(f"{asset} (webp): {exc}")
                print(f"warn webp companion failed for {asset}: {exc}", file=sys.stderr)

        if not args.dry_run:
            try:
                manifest[rel] = fingerprint(asset)
            except OSError as exc:
                stats.errors.append(f"{asset}: manifest update failed: {exc}")

    if not args.dry_run:
        try:
            save_manifest(manifest_path, manifest)
        except OSError as exc:
            print(f"warn: could not save manifest {manifest_path}: {exc}", file=sys.stderr)

    saved = stats.bytes_before - stats.bytes_after
    print()
    print("Summary")
    print(f"  scanned:    {stats.scanned}")
    print(f"  skipped:    {stats.skipped} (already optimized)")
    print(f"  optimized:  {stats.optimized}")
    print(f"  failed:     {stats.failed}")
    if stats.optimized:
        print(f"  size:       {fmt_bytes(stats.bytes_before)} -> {fmt_bytes(stats.bytes_after)} (saved {fmt_bytes(saved)})")
    if stats.webp_created:
        print(f"  webp:       {stats.webp_created} companions ({fmt_bytes(stats.webp_bytes)} total)")
    if stats.errors and args.verbose:
        print("  errors:")
        for line in stats.errors:
            print(f"    - {line}")

    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
