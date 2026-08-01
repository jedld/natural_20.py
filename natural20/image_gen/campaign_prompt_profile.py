"""Load optional per-campaign image prompt styles from ``asset_prompts.yml``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_TOKEN_STYLE = (
    "fantasy VTT token bust, close-up head and shoulders, face centered, fills frame, "
    "painterly, dramatic lighting, high-detail face"
)

DEFAULT_PORTRAIT_STYLE = (
    "painterly fantasy portrait, head and shoulders, face centered, dramatic lighting, no text"
)

DEFAULT_LOGIN_SCENE = (
    "medieval fantasy town, cobblestone, timber buildings, warm afternoon light"
)

DEFAULT_CHARACTER_SELECTION_SCENE = (
    "party of fantasy adventurers, dramatic group portrait, warm torchlight"
)

DEFAULT_SCENES: dict[str, str] = {
    "tavern": "medieval tavern, hearth glow, blurred patrons",
    "market": "market stall, canvas awning, timber buildings",
    "street": "cobblestone street, timber shops, afternoon sun",
    "town": "medieval fantasy town, warm afternoon light",
    "bedroom": "medieval adventurer bedroom, warm lamplight, simple furnishings",
    "laboratory": "wizard study, shelves of books, enchanted lamps",
    "dungeon": "stone dungeon corridor, dim torchlight",
    "basement": "stone basement, dim torchlight, dusty shelves",
    "cult": "underground cult chamber, rusted chains, dim torchlight",
}


@dataclass
class CampaignPromptProfile:
    """Campaign-local diffusion prompt fragments (from ``asset_prompts.yml``)."""

    token_style: str = DEFAULT_TOKEN_STYLE
    portrait_style: str = DEFAULT_PORTRAIT_STYLE
    login_scene: str = DEFAULT_LOGIN_SCENE
    character_selection_scene: str = DEFAULT_CHARACTER_SELECTION_SCENE
    scenes: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SCENES))

    def scene_backdrop(self, scene: str) -> str:
        normalized = (scene or "town").strip().lower()
        return self.scenes.get(normalized) or DEFAULT_SCENES.get(
            normalized, DEFAULT_SCENES["town"]
        )

    @classmethod
    def default(cls) -> CampaignPromptProfile:
        return cls(scenes=dict(DEFAULT_SCENES))

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> CampaignPromptProfile:
        if not isinstance(data, dict):
            return cls.default()

        scenes = dict(DEFAULT_SCENES)
        raw_scenes = data.get("scenes")
        if isinstance(raw_scenes, dict):
            for key, value in raw_scenes.items():
                text = str(value or "").strip()
                if text:
                    scenes[str(key).strip().lower()] = text

        profile = cls(
            token_style=str(data.get("token_style") or DEFAULT_TOKEN_STYLE).strip()
            or DEFAULT_TOKEN_STYLE,
            portrait_style=str(data.get("portrait_style") or DEFAULT_PORTRAIT_STYLE).strip()
            or DEFAULT_PORTRAIT_STYLE,
            login_scene=str(data.get("login_scene") or DEFAULT_LOGIN_SCENE).strip()
            or DEFAULT_LOGIN_SCENE,
            character_selection_scene=str(
                data.get("character_selection_scene") or DEFAULT_CHARACTER_SELECTION_SCENE
            ).strip()
            or DEFAULT_CHARACTER_SELECTION_SCENE,
            scenes=scenes,
        )
        return profile


def load_campaign_prompt_profile(campaign_root: Path | str) -> CampaignPromptProfile:
    """Read ``<campaign>/asset_prompts.yml`` when present; otherwise generic defaults."""
    root = Path(campaign_root).resolve()
    path = root / "asset_prompts.yml"
    if not path.is_file():
        return CampaignPromptProfile.default()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return CampaignPromptProfile.default()
    return CampaignPromptProfile.from_mapping(data if isinstance(data, dict) else {})
