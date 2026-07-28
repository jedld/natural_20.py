"""Tests for campaign voice profile generation."""

import json
from pathlib import Path

import yaml

from natural20.tts.campaign_voice_profiles import (
    VoiceProfileGenerationMode,
    build_heuristic_voice_block,
    build_llm_voice_block,
    discover_map_npc_candidates,
    discover_voice_candidates,
    generate_voice_profiles,
    load_campaign_voice_asset,
    resolve_generation_mode,
)


def test_build_heuristic_voice_block_from_backstory():
    data = {
        "kind": "goblin",
        "gender": "male",
        "race": ["humanoid", "goblin"],
        "backstory": "You are a mean goblin guard with a gravelly voice who tells people to stop touching things.",
        "dialog": True,
    }
    voice = build_heuristic_voice_block(data, label="Gabba", npc_type="goblin")
    assert "gabba" in voice["prompt"].lower() or "goblin" in voice["prompt"].lower()
    assert voice.get("gender") == "male"
    assert "gravelly" in voice.get("traits", [])


def test_discover_map_npc_candidates_templates_goblin_cave():
    repo = Path(__file__).resolve().parents[2]
    campaign = repo / "templates"
    candidates = discover_map_npc_candidates(campaign)
    keys = {c.key for c in candidates}
    assert "gabba" in keys
    gabba = next(c for c in candidates if c.key == "gabba")
    assert gabba.npc_type == "goblin"
    assert "gravelly" not in gabba.data.get("voice", {}).get("traits", [])


def test_generate_voice_profiles_writes_assets(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    campaign = tmp_path / "mini_campaign"
    (campaign / "maps").mkdir(parents=True)
    (campaign / "npcs").mkdir()
    (campaign / "game.yml").write_text("starting_map: maps/test.yml\n", encoding="utf-8")
    map_yaml = {
        "name": "Test Map",
        "legend": {
            "G": {
                "name": "Mara",
                "type": "npc",
                "sub_type": "human_guard",
                "overrides": {
                    "entity_uid": "mara_guard",
                    "backstory": "A stern town guard with a booming voice and dry humor.",
                    "dialog": True,
                },
            }
        },
    }
    (campaign / "maps" / "test.yml").write_text(yaml.safe_dump(map_yaml), encoding="utf-8")
    (campaign / "npcs" / "human_guard.yml").write_text(
        yaml.safe_dump(
            {
                "kind": "Guard",
                "description": "Generic human guard",
                "race": ["humanoid", "human"],
            }
        ),
        encoding="utf-8",
    )

    report = generate_voice_profiles(
        campaign,
        include_types=False,
        include_maps=True,
        only=["mara_guard"],
        force=True,
    )
    assert len(report.written) == 1
    asset = load_campaign_voice_asset(campaign, entity_uid="mara_guard")
    assert asset is not None
    assert "booming" in asset["voice"].get("traits", []) or "booming" in asset["voice"]["prompt"].lower()


def test_generate_voice_profiles_skips_existing_prompt(tmp_path):
    campaign = tmp_path / "camp"
    (campaign / "npcs").mkdir(parents=True)
    (campaign / "game.yml").write_text("name: test\n", encoding="utf-8")
    (campaign / "npcs" / "merchant.yml").write_text(
        yaml.safe_dump(
            {
                "kind": "Merchant",
                "description": "A friendly trader",
                "voice": {"prompt": "Existing custom voice"},
            }
        ),
        encoding="utf-8",
    )
    report = generate_voice_profiles(campaign, include_maps=False, all_types=True)
    assert len(report.skipped) == 1
    assert "already set" in report.skipped[0].reason


def test_discover_voice_candidates_types_only():
    repo = Path(__file__).resolve().parents[2]
    campaign = repo / "templates"
    candidates = discover_voice_candidates(campaign, include_maps=False)
    kinds = {c.npc_type.lower() for c in candidates}
    assert "goblin" in kinds


def test_build_llm_voice_block_uses_llm_json():
    data = {
        "kind": "goblin",
        "backstory": "Mean goblin guard who snarls at trespassers.",
        "dialog": True,
    }

    def fake_llm(messages):
        assert any("goblin" in m["content"].lower() for m in messages)
        return json.dumps(
            {
                "prompt": "Snarling goblin sentry with a nasal, aggressive rasp",
                "gender": "male",
                "age": "young",
                "traits": ["nasal", "aggressive", "snarling"],
                "style": "angry",
                "accent": None,
            }
        )

    voice = build_llm_voice_block(
        data,
        label="Gabba",
        npc_type="goblin",
        llm_send=fake_llm,
        heuristic_fallback=False,
    )
    assert "snarling" in voice["prompt"].lower()
    assert voice["traits"] == ["nasal", "aggressive", "snarling"]
    assert voice["style"] == "angry"


def test_build_llm_voice_block_no_fallback_raises():
    data = {"kind": "goblin", "dialog": True}

    def bad_llm(_messages):
        return "not json"

    try:
        build_llm_voice_block(
            data,
            label="Gabba",
            npc_type="goblin",
            llm_send=bad_llm,
            heuristic_fallback=False,
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_resolve_generation_mode_from_game_yml(tmp_path):
    campaign = tmp_path / "camp"
    campaign.mkdir()
    (campaign / "game.yml").write_text(
        "tts:\n  voice_profile_mode: llm\n",
        encoding="utf-8",
    )
    assert resolve_generation_mode(campaign) == VoiceProfileGenerationMode.LLM


def test_generate_voice_profiles_llm_mode(tmp_path):
    campaign = tmp_path / "camp"
    (campaign / "npcs").mkdir(parents=True)
    (campaign / "game.yml").write_text("name: test\n", encoding="utf-8")
    (campaign / "npcs" / "merchant.yml").write_text(
        yaml.safe_dump(
            {
                "kind": "Merchant",
                "description": "Friendly halfling trader with a singsong cadence.",
                "dialog": True,
            }
        ),
        encoding="utf-8",
    )

    def fake_llm(_messages):
        return json.dumps(
            {
                "prompt": "Cheerful halfling merchant, singsong cadence, warm tenor",
                "gender": "male",
                "age": "mature",
                "traits": ["cheerful", "singsong", "warm"],
                "style": "happy",
            }
        )

    report = generate_voice_profiles(
        campaign,
        mode=VoiceProfileGenerationMode.LLM,
        llm_send=fake_llm,
        include_maps=False,
        all_types=True,
        heuristic_fallback=False,
    )
    assert len(report.written) == 1
    assert report.written[0].generator_mode == "llm"
    assert "halfling" in report.written[0].voice["prompt"].lower()

