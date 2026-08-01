"""Tests for Image Gen MCP client and campaign asset generation."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from natural20.image_gen.campaign_assets import (
    discover_npc_defs,
    generate_campaign_assets,
    token_filename_for_npc,
)
from natural20.image_gen.mcp_client import ImageGenMcpClient, GeneratedImage
from natural20.image_gen.tokens import crop_for_token, make_circular_token


def _solid(size=64, color=(200, 40, 40, 255)) -> Image.Image:
    return Image.new("RGBA", (size, size), color)


def test_make_circular_token_transparent_corners_and_ring():
    token = make_circular_token(_solid(128), size=64, ring_width=3)
    assert token.size == (64, 64)
    assert token.mode == "RGBA"
    # Corner should be transparent; center opaque.
    assert token.getpixel((0, 0))[3] == 0
    assert token.getpixel((32, 32))[3] == 255
    # Ring pixels near edge should be non-transparent.
    assert token.getpixel((32, 1))[3] > 0


def test_crop_for_token_portrait_biases_toward_upper_face():
    """Tall portraits should crop the face region, not the geometric center."""
    img = Image.new("RGBA", (400, 520), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Bright "face" marker in upper third
    draw.ellipse((150, 80, 250, 180), fill=(255, 0, 0, 255))
    # Body marker lower down
    draw.rectangle((120, 320, 280, 500), fill=(0, 0, 255, 255))

    cropped = crop_for_token(img)
    assert cropped.size[0] == cropped.size[1]

    center = cropped.getpixel((cropped.size[0] // 2, cropped.size[1] // 2))
    # Center of token crop should be closer to red face than blue body.
    assert center[0] > center[2]

    center_crop = img.crop(
        (
            (400 - 400) // 2,
            (520 - 400) // 2,
            (400 - 400) // 2 + 400,
            (520 - 400) // 2 + 400,
        )
    )
    geo_center = center_crop.getpixel((center_crop.size[0] // 2, center_crop.size[1] // 2))
    assert geo_center[2] >= geo_center[0]  # geometric center hits more blue body


def test_mcp_parse_sse_message():
    raw = (
        ": ping\n\n"
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
    )
    parsed = ImageGenMcpClient._parse_sse_or_json(raw)
    assert parsed["result"]["ok"] is True


def test_mcp_image_from_content_base64():
    buf = io.BytesIO()
    _solid(32).save(buf, format="PNG")
    import base64

    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    image = ImageGenMcpClient._image_from_content(
        [{"type": "image", "mimeType": "image/png", "data": b64}]
    )
    assert image is not None
    assert image.size == (32, 32)


from natural20.image_gen.prompts import (
    CLIP_MAX_WORDS,
    campaign_asset_mood,
    fit_clip_prompt,
    npc_scene_portrait_prompt,
    npc_visual_description,
)
from natural20.image_gen.campaign_prompt_profile import load_campaign_prompt_profile


def test_npc_visual_description_prefers_outward_appearance():
    npc = {
        "description": "Tavern owner and gossip hub.",
        "outward_appearance": "Stout woman with steel-gray hair in a knot.",
    }
    assert npc_visual_description(npc) == "Stout woman with steel-gray hair in a knot."


def test_campaign_asset_mood_omits_long_story_description():
    meta = {
        "title": "A Wild Sheep Chase",
        "description": (
            "Finethir Shinebright, a transmutation wizard trapped as a sheep, needs heroes "
            "to recover his stolen Wand of True Polymorph from his treacherous apprentice."
        ),
        "asset_theme": "whimsical D&D one-shot, Prancing Flagon market town, warm afternoon light",
    }
    mood = campaign_asset_mood(meta)
    assert "Finethir" not in mood
    assert "Prancing Flagon" in mood


def test_fit_clip_prompt_limits_word_count():
    long_text = " ".join(f"word{i}" for i in range(120))
    prompt = fit_clip_prompt("Portrait of Pip", long_text, "tavern background")
    assert len(prompt.split()) <= CLIP_MAX_WORDS


def test_npc_scene_portrait_prompt_stays_within_clip_budget():
    profile = load_campaign_prompt_profile(Path("user_levels/wild_sheep_chase"))
    prompt = npc_scene_portrait_prompt(
        name="Pip",
        kind="Pip",
        description=(
            "Cheerful halfling woman barely four feet tall, quick on her feet with bright "
            "hazel eyes and a dusting of freckles across her nose. Chestnut curls escape a "
            "linen cap. Green wool dress under a white apron."
        ),
        race="halfling",
        scene="tavern",
        theme="whimsical D&D one-shot, Prancing Flagon market town, warm afternoon light",
        profile=profile,
    )
    assert len(prompt.split()) <= CLIP_MAX_WORDS
    assert "Finethir" not in prompt
    assert "warm natural light" in prompt


def test_load_campaign_prompt_profile_death_house(tmp_path: Path):
    campaign = Path("user_levels/death_house")
    if not campaign.is_dir():
        pytest.skip("death_house campaign missing")
    profile = load_campaign_prompt_profile(campaign)
    assert "gothic horror" in profile.token_style.lower()
    assert "Barovia" in profile.portrait_style
    assert "Svalich" in profile.login_scene
    assert "barovia" in profile.scene_backdrop("basement").lower()


def test_load_campaign_prompt_profile_defaults_without_file(tmp_path: Path):
    campaign = tmp_path / "bare"
    campaign.mkdir()
    profile = load_campaign_prompt_profile(campaign)
    assert profile.scene_backdrop("tavern") == "medieval tavern, hearth glow, blurred patrons"
    assert "dramatic lighting" in profile.token_style


def test_discover_outcasts_npcs():
    campaign = Path("user_levels/outcasts_path")
    if not campaign.is_dir():
        pytest.skip("outcasts_path missing")
    npcs = discover_npc_defs(campaign)
    kinds = {n.get("kind") for n in npcs}
    assert "Whisper" in kinds or "whisper" in {str(k).lower() for k in kinds}
    assert token_filename_for_npc({"kind": "LadyOphelia"}) == "token_ladyophelia.png"


def test_generate_campaign_assets_dry_run_and_mock(tmp_path: Path):
    campaign = tmp_path / "demo"
    (campaign / "npcs").mkdir(parents=True)
    (campaign / "npcs" / "guard.yml").write_text(
        "kind: Guard\ndescription: A weary gate guard.\nrace: [human]\nalignment: lawful_neutral\n",
        encoding="utf-8",
    )
    (campaign / "game.yml").write_text(
        "name: Demo\ndescription: Noir alley campaign.\n",
        encoding="utf-8",
    )
    (campaign / "index.json").write_text(
        json.dumps(
            {
                "title": "Demo Noir",
                "login_background": "demo_title.jpg",
                "selectable_characters": [
                    {
                        "name": "rogue",
                        "file": "characters/rogue.png",
                        "description": "A sly investigator.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return GeneratedImage(image=_solid(256, (30, 90, 160, 255)), summary="ok")

    report = generate_campaign_assets(
        campaign,
        tokens=True,
        background=True,
        portraits=True,
        force=True,
        dry_run=False,
        generator=fake_generate,
        quality="low",
    )
    assert not report.errors
    assert (campaign / "assets" / "token_guard.png").is_file()
    token = Image.open(campaign / "assets" / "token_guard.png")
    assert token.size == (256, 256)
    assert token.getpixel((0, 0))[3] == 0
    assert (campaign / "assets" / "demo_title.jpg").is_file()
    assert (campaign / "assets" / "characters" / "rogue.png").is_file()
    yaml_text = (campaign / "npcs" / "guard.yml").read_text(encoding="utf-8")
    assert "token_image: token_guard.png" in yaml_text
    assert any("portrait" in c.get("prompt", "").lower() or "VTT" in c.get("prompt", "") for c in calls)

    dry = generate_campaign_assets(
        campaign,
        tokens=True,
        background=False,
        portraits=False,
        dry_run=True,
        generator=fake_generate,
    )
    assert all(r.skipped for r in dry.results)
