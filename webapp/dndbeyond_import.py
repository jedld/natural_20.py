"""D&D Beyond character import helpers for the web character builder."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from beyond_importer import (  # noqa: E402
    BeyondImporter,
    parse_character_id_from_url,
)

__all__ = [
    "parse_character_id_from_url",
    "import_character_from_dndbeyond",
    "prepare_imported_pc_dict",
]


def import_character_from_dndbeyond(
    character_id: int,
    *,
    cobalt_token: Optional[str] = None,
    input_path: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Fetch (or load) a D&D Beyond character and convert it to engine YAML fields."""
    importer = BeyondImporter()
    if input_path:
        data = importer.load_character(input_path)
    else:
        data = importer.fetch_character(character_id, cobalt_token=cobalt_token)
    return importer.convert_to_yaml(data), list(importer.warnings)


def prepare_imported_pc_dict(pc: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """Ensure imported YAML has filenames/paths the webapp expects."""
    name = (pc.get("name") or "Unnamed").strip() or "Unnamed"
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    entity_uid = (pc.get("entity_uid") or safe_name).lower()
    entity_uid = re.sub(r"[^a-zA-Z0-9_\-]", "_", entity_uid)

    pc = dict(pc)
    pc["name"] = name
    pc["entity_uid"] = entity_uid
    pc.setdefault("hit_die", "inherit")
    pc.setdefault("group", "a")
    token_letter = (name.strip()[:1] or "P").upper()
    pc.setdefault("token", [token_letter])
    pc.setdefault("token_image", f"token_{entity_uid}.png")
    pc.setdefault("profile_image", f"characters/{entity_uid}.png")
    return pc, safe_name
