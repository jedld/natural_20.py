"""Create a new, bootable campaign skeleton (``index.json``, ``game.yml``, one empty map).

Used by ``start_web.sh --new <dir>`` and runnable directly::

    python -m natural20.campaign_scaffold user_levels/my_campaign --title "My Campaign"

Items, spells, classes, races and NPCs are not copied: campaigns fall back to the
bundled ``templates/`` for anything they do not define themselves.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MAP_NAME = "start"
DEFAULT_WIDTH = 20
DEFAULT_HEIGHT = 15
DEFAULT_TILE_SIZE = 70
DEFAULT_RULESET = "5e-2014"
LOGIN_BACKGROUND = "title.png"
DEFAULT_DM_LOGIN = {"name": "dm", "password": "admin", "role": ["dm"]}

CAMPAIGN_SUBDIRS = ("characters", "npcs", "items", "maps", "assets/maps")

DEFAULT_GROUPS: dict[str, Any] = {
    "a": {"default": True, "enemies": ["b"], "neutral": ["c"]},
    "b": {"enemies": ["a"], "neutral": ["c"]},
    "c": {"neutral": ["a", "b"]},
}


class CampaignExistsError(FileExistsError):
    """Raised when the target directory already holds a campaign."""


def title_from_slug(slug: str) -> str:
    words = [w for w in re.split(r"[_\-\s]+", slug) if w]
    return " ".join(w.capitalize() for w in words) or "New Campaign"


def empty_map_document(
    name: str,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    *,
    description: str | None = None,
    illumination: float = 1.0,
) -> dict[str, Any]:
    """Return a map YAML document of plain floor tiles with no entities."""
    width = max(2, min(int(width), 100))
    height = max(2, min(int(height), 100))
    return {
        "name": name,
        "description": description or f"Empty map {name}",
        "map": {
            "illumination": max(0.0, min(1.0, float(illumination))),
            "base": ["." * width for _ in range(height)],
        },
        "legend": {},
        "player": [],
    }


def scaffold_campaign(
    path: str | os.PathLike,
    *,
    title: str | None = None,
    map_name: str = DEFAULT_MAP_NAME,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    ruleset: str = DEFAULT_RULESET,
) -> Path:
    """Create a minimal campaign at ``path`` and return its absolute root.

    Refuses to touch a directory that already has an ``index.json`` or ``game.yml``;
    an empty or missing directory is fine.
    """
    root = Path(path).expanduser().resolve()
    if (root / "index.json").exists() or (root / "game.yml").exists():
        raise CampaignExistsError(f"Campaign already exists at {root}")
    if not re.match(r"^[a-z0-9_\-]+$", map_name):
        raise ValueError(f"Invalid map name: {map_name!r}")

    title = (title or "").strip() or title_from_slug(root.name)
    map_ref = f"maps/{map_name}"

    root.mkdir(parents=True, exist_ok=True)
    for sub in CAMPAIGN_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)

    map_doc = empty_map_document(map_name, width, height, description=f"Starting area of {title}.")
    _write_yaml(root / f"{map_ref}.yml", map_doc)

    game = {
        "name": title,
        "title": [title.upper()],
        "description": f"{title} — a new Natural20 campaign.",
        "ruleset": ruleset,
        "players": 4,
        "starting_map": map_ref,
        "maps": {map_name: map_ref},
        "player_profiles": "characters",
        "groups": DEFAULT_GROUPS,
    }
    _write_yaml(root / "game.yml", game)

    index = {
        "tile_size": DEFAULT_TILE_SIZE,
        "width": len(map_doc["map"]["base"][0]),
        "height": len(map_doc["map"]["base"]),
        "title": title,
        "login_background": LOGIN_BACKGROUND,
        "map": map_ref,
        "autosave": False,
        "soundtracks": [],
        "logins": [DEFAULT_DM_LOGIN],
        "default_controllers": [],
    }
    _write_placeholder_image(root / "assets" / LOGIN_BACKGROUND, title)
    with open(root / "index.json", "w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2)
        handle.write("\n")
    return root


def _write_placeholder_image(path: Path, title: str) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1280, 720), color=(24, 22, 36))
    ImageDraw.Draw(img).text((40, 40), title, fill=(220, 210, 180))
    img.save(path)


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a new, bootable Natural20 campaign.")
    parser.add_argument("path", help="Campaign directory to create (e.g. user_levels/my_campaign)")
    parser.add_argument("--title", help="Display title (default: derived from the directory name)")
    parser.add_argument("--map-name", default=DEFAULT_MAP_NAME, help="Starting map id (default: start)")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--ruleset", default=DEFAULT_RULESET, help="5e-2014 (default) or 5e-2024")
    parser.add_argument("--if-missing", action="store_true",
                        help="Exit successfully without changes when the campaign already exists")
    args = parser.parse_args(argv)
    try:
        root = scaffold_campaign(
            args.path, title=args.title, map_name=args.map_name,
            width=args.width, height=args.height, ruleset=args.ruleset,
        )
    except CampaignExistsError as exc:
        if args.if_missing:
            print(f"{exc}; using it as-is.", file=sys.stderr)
            return 0
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Created campaign at {root} (DM login: dm / admin)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
