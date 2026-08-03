"""Tests for NPC gallery image generation helpers."""

from pathlib import Path

from natural20.image_gen.campaign_assets import (
    build_gallery_image_prompt,
    find_npc_def,
    npc_gallery_entries,
)
from natural20.image_gen.campaign_prompt_profile import load_campaign_prompt_profile


def test_find_npc_def_and_gallery_entries():
    campaign = Path("user_levels/wild_sheep_chase")
    if not campaign.is_dir():
        return
    npc = find_npc_def(campaign, "pip_barmaid")
    assert npc is not None
    entries = npc_gallery_entries(npc)
    ids = {entry["id"] for entry in entries}
    assert "bedroom_doorway" in ids
    assert "bedroom_lounging" in ids


def test_build_gallery_image_prompt_uses_entry_override():
    campaign = Path("user_levels/wild_sheep_chase")
    if not campaign.is_dir():
        return
    npc = find_npc_def(campaign, "pip_barmaid")
    assert npc is not None
    entry = next(e for e in npc_gallery_entries(npc) if e["id"] == "bedroom_doorway")
    profile = load_campaign_prompt_profile(campaign)
    prompt = build_gallery_image_prompt(npc, entry, theme="tavern mood", prompt_profile=profile)
    assert "doorway" in prompt.lower()
    assert "halfling" in prompt.lower()
