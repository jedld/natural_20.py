"""Generate and persist NPC voice profiles as campaign assets."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import yaml

from natural20.image_gen.campaign_assets import discover_npc_defs
from natural20.yaml_loader import load_campaign_resource_path, load_yaml, templates_root
from webapp.tts.npc_voice import (
    infer_voice_profile,
    normalize_age_band,
    normalize_gender,
    save_voice_config,
)

VOICE_PROFILES_DIR = Path("assets") / "voice_profiles"
INDEX_FILENAME = "index.json"


class VoiceProfileGenerationMode(str, Enum):
    """How voice profile fields are authored."""

    HEURISTIC = "heuristic"
    LLM = "llm"


def resolve_generation_mode(
    campaign: Optional[Path] = None,
    *,
    cli_mode: Optional[str] = None,
) -> VoiceProfileGenerationMode:
    """
    Resolve generation mode from CLI > env > campaign game.yml > heuristic default.

    Env: ``N20_VOICE_PROFILE_MODE=llm|heuristic``
    Campaign YAML: ``tts.voice_profile_mode`` or top-level ``voice_profile_mode``
    """
    if cli_mode:
        try:
            return VoiceProfileGenerationMode(str(cli_mode).strip().lower())
        except ValueError:
            pass

    env_mode = (os.environ.get("N20_VOICE_PROFILE_MODE") or "").strip().lower()
    if env_mode:
        try:
            return VoiceProfileGenerationMode(env_mode)
        except ValueError:
            pass

    if campaign is not None:
        game_path = Path(campaign) / "game.yml"
        if game_path.is_file():
            game = load_yaml(game_path, campaign_root=campaign) or {}
            if isinstance(game, dict):
                tts = game.get("tts") if isinstance(game.get("tts"), dict) else {}
                for key in ("voice_profile_mode", "voice_profiles_mode"):
                    raw = tts.get(key) if isinstance(tts, dict) else None
                    if raw is None:
                        raw = game.get(key)
                    if raw:
                        try:
                            return VoiceProfileGenerationMode(str(raw).strip().lower())
                        except ValueError:
                            pass

    return VoiceProfileGenerationMode.HEURISTIC

# Adjectives and delivery cues mined from narrative text for traits / prompts.
_VOICE_ADJECTIVES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gravelly", ("gravelly", "gruff", "gravel", "rough-edged", "rough voiced")),
    ("raspy", ("raspy", "hoarse", "croaky", "husky")),
    ("booming", ("booming", "thunderous", "loud", "commanding")),
    ("soft", ("soft", "gentle", "mellow", "tender")),
    ("warm", ("warm", "kind", "friendly", "welcoming")),
    ("cold", ("cold", "icy", "detached", "clinical")),
    ("nervous", ("nervous", "anxious", "timid", "fearful", "shaky")),
    ("sinister", ("sinister", "menacing", "creepy", "ominous", "threatening")),
    ("scholarly", ("scholarly", "learned", "erudite", "measured", "precise")),
    ("jovial", ("jovial", "cheerful", "laughing", "boisterous", "merry")),
    ("weary", ("weary", "tired", "exhausted", "world-weary")),
    ("aristocratic", ("aristocratic", "refined", "noble", "courtly", "poised")),
    ("streetwise", ("streetwise", "cunning", "sly", "wry", "dry humor")),
    ("pious", ("pious", "devout", "solemn", "reverent")),
    ("aggressive", ("aggressive", "fierce", "snarling", "hostile", "belligerent")),
)

_ALIGNMENT_STYLE: dict[str, str] = {
    "lawful_good": "calm",
    "neutral_good": "warm",
    "chaotic_good": "energetic",
    "lawful_neutral": "measured",
    "true_neutral": "calm",
    "neutral": "calm",
    "chaotic_neutral": "wry",
    "lawful_evil": "cold",
    "neutral_evil": "aggressive",
    "chaotic_evil": "angry",
}

_NON_SPEAKING_KINDS = frozenset(
    {
        "bat",
        "boar",
        "wolf",
        "owl",
        "cat",
        "rat",
        "giant_rat",
        "animated_broom",
        "animated_armor",
        "heart",
        "shamblingmound",
    }
)


@dataclass
class NpcVoiceCandidate:
    """One NPC or map instance that may receive a generated voice profile."""

    key: str
    label: str
    npc_type: str
    source: str
    entity_uid: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)
    map_name: Optional[str] = None

    @property
    def profile_id(self) -> str:
        if self.entity_uid:
            return str(self.entity_uid)
        return self.key


@dataclass
class GeneratedVoiceProfile:
    profile_id: str
    label: str
    npc_type: str
    source: str
    voice: dict[str, Any]
    entity_uid: Optional[str] = None
    skipped: bool = False
    reason: str = ""
    generator_mode: str = VoiceProfileGenerationMode.HEURISTIC.value


@dataclass
class VoiceProfileReport:
    results: list[GeneratedVoiceProfile] = field(default_factory=list)

    @property
    def written(self) -> list[GeneratedVoiceProfile]:
        return [r for r in self.results if not r.skipped]

    @property
    def skipped(self) -> list[GeneratedVoiceProfile]:
        return [r for r in self.results if r.skipped]


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower())
    return text.strip("_") or "npc"


def _race_label(raw: Any) -> str:
    if isinstance(raw, list) and raw:
        return str(raw[-1] if len(raw) > 1 else raw[0]).strip()
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _text_fields(data: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in (
        "backstory",
        "description",
        "outward_appearance",
        "personality",
        "conversation_prompt",
        "notes",
    ):
        value = data.get(key)
        if not value:
            continue
        fields.append(str(value).strip())
    voice = data.get("voice")
    if isinstance(voice, dict) and voice.get("prompt"):
        fields.append(str(voice["prompt"]).strip())
    return [f for f in fields if f]


def _text_blob(data: dict[str, Any], label: str = "") -> str:
    parts = _text_fields(data)
    if label:
        parts.append(label)
    kind = str(data.get("kind") or "").strip()
    if kind:
        parts.append(kind.replace("_", " "))
    return "\n".join(parts)


def _extract_traits(text: str, limit: int = 6) -> list[str]:
    haystack = (text or "").lower()
    found: list[str] = []
    for trait, hints in _VOICE_ADJECTIVES:
        if any(hint in haystack for hint in hints):
            found.append(trait)
        if len(found) >= limit:
            break
    return found


def _infer_style(data: dict[str, Any], text: str) -> str:
    voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
    if voice.get("style"):
        return str(voice["style"]).strip()
    alignment = str(data.get("alignment") or "").strip().lower()
    if alignment in _ALIGNMENT_STYLE:
        return _ALIGNMENT_STYLE[alignment]
    haystack = text.lower()
    if any(word in haystack for word in ("angry", "furious", "rage", "snarl")):
        return "angry"
    if any(word in haystack for word in ("whisper", "quiet", "secret", "hushed")):
        return "whisper"
    if any(word in haystack for word in ("laugh", "jolly", "cheerful", "jovial")):
        return "happy"
    return "calm"


def _infer_accent(data: dict[str, Any], text: str) -> Optional[str]:
    voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
    if voice.get("accent"):
        return str(voice["accent"]).strip()
    haystack = text.lower()
    accent_map = {
        "british": ("british", "english accent", "posh"),
        "irish": ("irish",),
        "scottish": ("scottish", "scots"),
        "french": ("french",),
        "german": ("german",),
        "russian": ("russian", "eastern european"),
        "romanian": ("romanian",),
    }
    for accent, hints in accent_map.items():
        if any(h in haystack for h in hints):
            return accent
    return None


def _is_speakable(data: dict[str, Any], npc_type: str) -> bool:
    if data.get("conversation_handler"):
        return True
    if data.get("dialog") or data.get("dialogue"):
        return True
    if data.get("conversation_buffer"):
        return True
    if _text_fields(data):
        return True
    if npc_type.lower() in _NON_SPEAKING_KINDS:
        return False
    # Humanoid templates are often used for guards/merchants even without backstory.
    race = data.get("race") or []
    race_text = " ".join(race) if isinstance(race, list) else str(race)
    if any(token in race_text.lower() for token in ("human", "elf", "dwarf", "halfling", "gnome", "tiefling")):
        return True
    return False


def _role_phrase(data: dict[str, Any], label: str, npc_type: str) -> str:
    kind = str(data.get("kind") or npc_type or label or "NPC").replace("_", " ").strip()
    if label and label.lower() not in kind.lower() and label.lower() != "_auto_":
        return f"{label}, {kind}"
    return kind


def build_heuristic_voice_block(
    data: dict[str, Any],
    *,
    label: str,
    npc_type: str,
    default_strategy: str = "auto",
    default_provider: Optional[str] = None,
) -> dict[str, Any]:
    """Build a voice YAML block from NPC narrative fields (no LLM)."""
    text = _text_blob(data, label=label)
    inferred = infer_voice_profile(text, npc_data=data)
    traits = _extract_traits(text)
    role = _role_phrase(data, label, npc_type)

    demo: list[str] = []
    if inferred.get("age_band") == "elderly":
        demo.append("elderly")
    elif inferred.get("age_band") == "young":
        demo.append("young")
    elif inferred.get("age_band") == "mature":
        demo.append("mature")
    if inferred.get("gender") == "male":
        demo.append("male")
    elif inferred.get("gender") == "female":
        demo.append("female")
    race = _race_label(inferred.get("race") or data.get("race"))
    if race and race.lower() not in ("humanoid",):
        demo.append(race)

    trait_clause = ", ".join(traits[:4])
    if trait_clause:
        prompt = f"{role} with a {trait_clause} voice"
    elif demo:
        prompt = f"{' '.join(demo)} {role}"
    else:
        prompt = f"Fantasy {role}"

    # Trim overly long prompts while keeping the role visible.
    if len(prompt) > 220:
        prompt = prompt[:217].rsplit(" ", 1)[0] + "..."

    voice: dict[str, Any] = {
        "prompt": prompt,
        "gender": normalize_gender(data.get("gender") or inferred.get("gender")),
        "age": normalize_age_band(
            (data.get("voice") or {}).get("age")
            if isinstance(data.get("voice"), dict)
            else None
        ) or inferred.get("age_band"),
        "style": _infer_style(data, text),
        "traits": traits,
        "strategy": default_strategy,
        "language": "en",
        "locked": True,
    }
    accent = _infer_accent(data, text)
    if accent:
        voice["accent"] = accent
    if default_provider:
        voice["provider"] = default_provider

    existing = data.get("voice")
    if isinstance(existing, dict):
        for key in ("reference_audio", "provider", "strategy", "language", "accent"):
            if existing.get(key) is not None and voice.get(key) in (None, "auto", "en"):
                voice[key] = existing[key]
        if existing.get("prompt") and not traits:
            voice["prompt"] = str(existing["prompt"]).strip()

    return {k: v for k, v in voice.items() if v is not None}


def _parse_llm_json(text: str) -> Optional[dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _load_voice_profile_system_prompt() -> str:
    prompt_path = (
        Path(__file__).resolve().parents[2] / "webapp" / "prompts" / "voice_profile_generation_system.txt"
    )
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8").strip()
    return (
        "You create concise TTS voice profiles for D&D NPCs. "
        "Return ONLY valid JSON with keys: prompt, gender, age, traits, style, accent."
    )


def _voice_block_shell(
    data: dict[str, Any],
    *,
    label: str,
    npc_type: str,
    default_strategy: str = "auto",
    default_provider: Optional[str] = None,
) -> dict[str, Any]:
    """Shared defaults merged into heuristic or LLM-authored voice blocks."""
    text = _text_blob(data, label=label)
    inferred = infer_voice_profile(text, npc_data=data)
    voice: dict[str, Any] = {
        "prompt": "",
        "gender": normalize_gender(data.get("gender") or inferred.get("gender")),
        "age": normalize_age_band(
            (data.get("voice") or {}).get("age")
            if isinstance(data.get("voice"), dict)
            else None
        ) or inferred.get("age_band"),
        "style": _infer_style(data, text),
        "traits": [],
        "strategy": default_strategy,
        "language": "en",
        "locked": True,
    }
    accent = _infer_accent(data, text)
    if accent:
        voice["accent"] = accent
    if default_provider:
        voice["provider"] = default_provider

    existing = data.get("voice")
    if isinstance(existing, dict):
        for key in ("reference_audio", "provider", "strategy", "language", "accent"):
            if existing.get(key) is not None and voice.get(key) in (None, "auto", "en"):
                voice[key] = existing[key]
    return voice


def _voice_block_from_llm_parsed(
    parsed: dict[str, Any],
    shell: dict[str, Any],
) -> dict[str, Any]:
    voice = dict(shell)
    prompt = str(parsed.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("LLM response missing prompt")
    voice["prompt"] = prompt[:220]
    if parsed.get("gender"):
        voice["gender"] = normalize_gender(parsed.get("gender"))
    if parsed.get("age"):
        voice["age"] = normalize_age_band(parsed.get("age"))
    if parsed.get("style"):
        voice["style"] = str(parsed["style"]).strip()
    traits = parsed.get("traits")
    if isinstance(traits, list):
        voice["traits"] = [str(t).strip() for t in traits if str(t).strip()][:6]
    elif isinstance(traits, str) and traits.strip():
        voice["traits"] = [part.strip() for part in traits.split(",") if part.strip()][:6]
    if parsed.get("accent"):
        voice["accent"] = str(parsed["accent"]).strip()
    return {k: v for k, v in voice.items() if v is not None}


def build_llm_voice_block(
    data: dict[str, Any],
    *,
    label: str,
    npc_type: str,
    llm_send: Callable[[list[dict[str, str]]], str],
    default_strategy: str = "auto",
    default_provider: Optional[str] = None,
    heuristic_fallback: bool = True,
) -> dict[str, Any]:
    """
    Author a voice block with an LLM from NPC narrative context.

    When ``heuristic_fallback`` is False, failures propagate as ValueError.
    """
    text = _text_blob(data, label=label)
    shell = _voice_block_shell(
        data,
        label=label,
        npc_type=npc_type,
        default_strategy=default_strategy,
        default_provider=default_provider,
    )
    alignment = str(data.get("alignment") or "").strip()
    race = _race_label(data.get("race"))
    system = _load_voice_profile_system_prompt()
    user = (
        f"NPC label: {label}\n"
        f"NPC type / kind: {npc_type}\n"
        f"Race: {race or 'unknown'}\n"
        f"Alignment: {alignment or 'unknown'}\n\n"
        f"Narrative context:\n{text[:2200]}\n\n"
        "Write a TTS voice profile JSON for this NPC."
    )
    try:
        raw = llm_send(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        parsed = _parse_llm_json(raw)
        if not parsed:
            raise ValueError("LLM response was not valid JSON")
        return _voice_block_from_llm_parsed(parsed, shell)
    except Exception as exc:
        if not heuristic_fallback:
            raise ValueError(f"LLM voice profile generation failed: {exc}") from exc
        fallback = build_heuristic_voice_block(
            data,
            label=label,
            npc_type=npc_type,
            default_strategy=default_strategy,
            default_provider=default_provider,
        )
        fallback["meta_note"] = f"llm_fallback: {exc}"
        return fallback


def discover_map_npc_candidates(campaign: Path) -> list[NpcVoiceCandidate]:
    """Find named NPC map instances with overrides (backstory, dialog, etc.)."""
    found: list[NpcVoiceCandidate] = []
    maps_dir = campaign / "maps"
    map_files: list[Path] = []
    if maps_dir.is_dir():
        map_files = sorted(maps_dir.glob("**/*.yml"))
    else:
        game_yml = campaign / "game.yml"
        if game_yml.is_file():
            game = load_yaml(game_yml, campaign_root=campaign) or {}
            start = str(game.get("starting_map") or "").strip()
            if start:
                rel = Path(start)
                candidate = campaign / rel
                if candidate.is_file():
                    map_files = [candidate]
                else:
                    template_candidate = templates_root() / rel
                    if template_candidate.is_file():
                        map_files = [template_candidate]

    for map_path in map_files:
        map_data = load_yaml(map_path, campaign_root=campaign) or {}
        if not isinstance(map_data, dict):
            continue
        map_name = str(map_data.get("name") or map_path.stem)
        legend = map_data.get("legend") or {}
        if not isinstance(legend, dict):
            continue
        for _symbol, entry in legend.items():
            if not isinstance(entry, dict) or entry.get("type") != "npc":
                continue
            npc_type = str(entry.get("sub_type") or entry.get("npc_type") or entry.get("name") or "").strip()
            if not npc_type or npc_type == "_auto_":
                continue
            overrides = entry.get("overrides") if isinstance(entry.get("overrides"), dict) else {}
            base: dict[str, Any] = {}
            try:
                base = load_campaign_resource_path(campaign, f"npcs/{npc_type}.yml") or {}
            except FileNotFoundError:
                base = {}
            if not isinstance(base, dict):
                base = {}
            merged = {**base, **overrides}
            merged.setdefault("kind", base.get("kind") or npc_type)
            label = str(entry.get("name") or overrides.get("label") or merged.get("label") or npc_type)
            if label == "_auto_":
                label = npc_type.replace("_", " ").title()
            entity_uid = overrides.get("entity_uid") or entry.get("entity_uid")
            key = str(entity_uid or f"map_{_slug(map_name)}_{_slug(label)}_{_slug(npc_type)}")
            found.append(
                NpcVoiceCandidate(
                    key=key,
                    label=label,
                    npc_type=npc_type,
                    source=str(map_path.relative_to(campaign)) if campaign in map_path.parents else str(map_path),
                    entity_uid=str(entity_uid) if entity_uid else None,
                    data=merged,
                    map_name=map_name,
                )
            )
    return found


def discover_voice_candidates(
    campaign: Path,
    *,
    include_types: bool = True,
    include_maps: bool = True,
    only: Optional[set[str]] = None,
) -> list[NpcVoiceCandidate]:
    """Collect NPC type defs and map instances for voice generation."""
    candidates: dict[str, NpcVoiceCandidate] = {}

    if include_types:
        for npc in discover_npc_defs(campaign):
            npc_type = str(npc.get("kind") or npc.get("_file_stem") or "npc")
            key = f"type_{_slug(npc_type)}"
            label = str(npc.get("label") or npc.get("kind") or npc_type).replace("_", " ").title()
            candidates[key] = NpcVoiceCandidate(
                key=key,
                label=label,
                npc_type=npc_type,
                source=str(npc.get("_source") or f"npcs/{npc_type}.yml"),
                data=npc,
            )

    if include_maps:
        for inst in discover_map_npc_candidates(campaign):
            candidates[inst.key] = inst

    ordered = list(candidates.values())
    if only:
        wanted = {part.strip().lower() for part in only if part.strip()}
        ordered = [
            c
            for c in ordered
            if c.profile_id.lower() in wanted
            or c.npc_type.lower() in wanted
            or c.label.lower() in wanted
            or c.key.lower() in wanted
        ]
    return ordered


def _voice_asset_path(campaign: Path, profile_id: str) -> Path:
    return campaign / VOICE_PROFILES_DIR / f"{_slug(profile_id)}.yml"


def load_campaign_voice_asset(
    campaign_root: str | Path,
    *,
    entity_uid: Optional[str] = None,
    npc_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Load a generated voice asset by entity uid or NPC type."""
    campaign = Path(campaign_root)
    index_path = campaign / VOICE_PROFILES_DIR / INDEX_FILENAME
    candidates: list[str] = []
    if entity_uid:
        candidates.append(str(entity_uid))
    if npc_type:
        candidates.append(f"type_{_slug(npc_type)}")
        candidates.append(_slug(npc_type))

    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index = {}
        entries = index.get("entries") if isinstance(index, dict) else {}
        if isinstance(entries, dict):
            for key in candidates:
                entry = entries.get(key)
                if isinstance(entry, dict) and entry.get("file"):
                    path = campaign / VOICE_PROFILES_DIR / str(entry["file"])
                    if path.is_file():
                        data = load_yaml(path, campaign_root=campaign) or {}
                        if isinstance(data, dict) and isinstance(data.get("voice"), dict):
                            return data

    for key in candidates:
        path = _voice_asset_path(campaign, key)
        if path.is_file():
            data = load_yaml(path, campaign_root=campaign) or {}
            if isinstance(data, dict) and isinstance(data.get("voice"), dict):
                return data
    return None


def _existing_voice_prompt(data: dict[str, Any]) -> Optional[str]:
    voice = data.get("voice")
    if isinstance(voice, dict) and str(voice.get("prompt") or "").strip():
        return str(voice["prompt"]).strip()
    return None


def generate_voice_profiles(
    campaign: Path,
    *,
    mode: VoiceProfileGenerationMode | str | None = None,
    use_llm: bool = False,
    llm_send: Optional[Callable[[list[dict[str, str]]], str]] = None,
    heuristic_fallback: bool = True,
    default_strategy: str = "auto",
    default_provider: Optional[str] = None,
    include_types: bool = True,
    include_maps: bool = True,
    only: Optional[Iterable[str]] = None,
    all_types: bool = False,
    force: bool = False,
    dry_run: bool = False,
    update_yaml: bool = False,
    write_assets: bool = True,
) -> VoiceProfileReport:
    """Generate voice profiles and write them under campaign assets (and optionally NPC YAML)."""
    campaign = campaign.resolve()
    resolved_mode = mode
    if resolved_mode is None:
        resolved_mode = VoiceProfileGenerationMode.LLM if use_llm else None
    if isinstance(resolved_mode, str):
        resolved_mode = VoiceProfileGenerationMode(resolved_mode.strip().lower())
    elif resolved_mode is None:
        resolved_mode = resolve_generation_mode(campaign)

    if resolved_mode == VoiceProfileGenerationMode.LLM and llm_send is None:
        llm_send = make_voice_profile_llm_sender()

    report = VoiceProfileReport()
    only_set = {str(x) for x in only} if only else None
    candidates = discover_voice_candidates(
        campaign,
        include_types=include_types,
        include_maps=include_maps,
        only=only_set,
    )

    for candidate in candidates:
        data = candidate.data
        if not all_types and not _is_speakable(data, candidate.npc_type):
            report.results.append(
                GeneratedVoiceProfile(
                    profile_id=candidate.profile_id,
                    label=candidate.label,
                    npc_type=candidate.npc_type,
                    source=candidate.source,
                    entity_uid=candidate.entity_uid,
                    voice={},
                    skipped=True,
                    reason="not speakable (use --all-types to include)",
                )
            )
            continue

        if not force and _existing_voice_prompt(data):
            report.results.append(
                GeneratedVoiceProfile(
                    profile_id=candidate.profile_id,
                    label=candidate.label,
                    npc_type=candidate.npc_type,
                    source=candidate.source,
                    entity_uid=candidate.entity_uid,
                    voice=data.get("voice") if isinstance(data.get("voice"), dict) else {},
                    skipped=True,
                    reason="voice.prompt already set (use --force)",
                )
            )
            continue

        generator_mode = resolved_mode.value
        try:
            if resolved_mode == VoiceProfileGenerationMode.LLM:
                if llm_send is None:
                    raise ValueError("LLM mode requires a configured LLM provider")
                voice = build_llm_voice_block(
                    data,
                    label=candidate.label,
                    npc_type=candidate.npc_type,
                    llm_send=llm_send,
                    default_strategy=default_strategy,
                    default_provider=default_provider,
                    heuristic_fallback=heuristic_fallback,
                )
            else:
                voice = build_heuristic_voice_block(
                    data,
                    label=candidate.label,
                    npc_type=candidate.npc_type,
                    default_strategy=default_strategy,
                    default_provider=default_provider,
                )
        except ValueError as exc:
            report.results.append(
                GeneratedVoiceProfile(
                    profile_id=candidate.profile_id,
                    label=candidate.label,
                    npc_type=candidate.npc_type,
                    source=candidate.source,
                    entity_uid=candidate.entity_uid,
                    voice={},
                    skipped=True,
                    reason=str(exc),
                    generator_mode=generator_mode,
                )
            )
            continue

        result = GeneratedVoiceProfile(
            profile_id=candidate.profile_id,
            label=candidate.label,
            npc_type=candidate.npc_type,
            source=candidate.source,
            entity_uid=candidate.entity_uid,
            voice=voice,
            generator_mode=generator_mode,
        )
        report.results.append(result)

        if dry_run:
            continue

        if write_assets:
            _write_voice_asset(
                campaign,
                result,
                narrative_excerpt=_text_blob(data, candidate.label)[:400],
            )

        if update_yaml and candidate.entity_uid is None and candidate.source.startswith("npcs/"):
            _update_npc_yaml_voice(campaign, candidate, voice)

    if write_assets and not dry_run:
        _write_voice_index(campaign, report)

    return report


def _write_voice_asset(
    campaign: Path,
    result: GeneratedVoiceProfile,
    *,
    narrative_excerpt: str,
) -> None:
    out_dir = campaign / VOICE_PROFILES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_slug(result.profile_id)}.yml"
    payload = {
        "profile_id": result.profile_id,
        "label": result.label,
        "npc_type": result.npc_type,
        "entity_uid": result.entity_uid,
        "source": result.source,
        "voice": result.voice,
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "generate_voice_profiles",
            "generator_mode": result.generator_mode,
            "narrative_excerpt": narrative_excerpt,
        },
    }
    path = out_dir / filename
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_voice_index(campaign: Path, report: VoiceProfileReport) -> None:
    out_dir = campaign / VOICE_PROFILES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, Any] = {}
    for result in report.written:
        entries[result.profile_id] = {
            "file": f"{_slug(result.profile_id)}.yml",
            "label": result.label,
            "npc_type": result.npc_type,
            "entity_uid": result.entity_uid,
            "source": result.source,
        }
    index_path = out_dir / INDEX_FILENAME
    existing: dict[str, Any] = {"version": 1, "entries": {}}
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except json.JSONDecodeError:
            pass
    merged_entries = dict(existing.get("entries") or {})
    merged_entries.update(entries)
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "entries": merged_entries,
    }
    index_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _update_npc_yaml_voice(campaign: Path, candidate: NpcVoiceCandidate, voice: dict[str, Any]) -> None:
    rel = candidate.source
    if not rel.startswith("npcs/"):
        return
    path = campaign / rel
    if not path.is_file():
        return
    data = load_yaml(path, campaign_root=campaign) or {}
    if not isinstance(data, dict):
        return
    save_voice_config(data, voice)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _resolve_llm_provider_name(*, prefer_npc: bool) -> str:
    if prefer_npc:
        enabled = os.environ.get("NPC_LLM_ENABLED", "1")
        if str(enabled).strip().lower() not in {"0", "no", "false", "disabled"}:
            npc_provider = (os.environ.get("NPC_LLM_PROVIDER") or "").strip().lower()
            if npc_provider:
                return npc_provider
    return (os.environ.get("LLM_PROVIDER") or "ollama").strip().lower()


def _provider_config(provider: str, *, prefer_npc: bool) -> dict[str, Any]:
    prefix = "NPC_" if prefer_npc else ""
    fallback_prefix = "" if prefer_npc else "NPC_"

    def _get(name: str, dm_name: Optional[str] = None) -> Optional[str]:
        for key in (f"{prefix}{name}", f"{fallback_prefix}{name}", name):
            value = os.environ.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        if dm_name:
            value = os.environ.get(dm_name)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    if provider == "openai":
        return {
            "api_key": _get("API_KEY", "OPENAI_API_KEY"),
            "model": _get("MODEL", "OPENAI_MODEL") or "gpt-4o-mini",
            "base_url": _get("BASE_URL", "OPENAI_BASE_URL"),
        }
    if provider == "anthropic":
        return {
            "api_key": _get("API_KEY", "ANTHROPIC_API_KEY"),
            "model": _get("MODEL", "ANTHROPIC_MODEL") or "claude-3-5-haiku-latest",
        }
    if provider in ("llama_cpp", "llama.cpp", "llamacpp"):
        config = {
            "base_url": _get("BASE_URL", "LLAMA_CPP_BASE_URL") or "http://localhost:8011",
            "api_key": _get("API_KEY", "LLAMA_CPP_API_KEY") or "llama-cpp",
        }
        model = _get("MODEL", "LLAMA_CPP_MODEL") or os.environ.get("N20_LLM_MODEL")
        if model:
            config["model"] = model
        return config
    return {
        "base_url": _get("BASE_URL", "OLLAMA_BASE_URL") or "http://localhost:11434",
        "model": _get("MODEL", "OLLAMA_MODEL") or "llama3.2",
    }


def make_voice_profile_llm_sender(*, prefer_npc: bool = True) -> Callable[[list[dict[str, str]]], str]:
    """
    Build an LLM send callable for voice profile generation.

    Uses NPC LLM env vars by default (``NPC_LLM_PROVIDER``, ``NPC_MODEL``, …),
    falling back to DM ``LLM_PROVIDER`` when NPC vars are unset.
    Override with ``N20_VOICE_PROFILE_LLM=dm`` to force DM provider.
    """
    prefer = prefer_npc
    override = (os.environ.get("N20_VOICE_PROFILE_LLM") or "").strip().lower()
    if override == "dm":
        prefer = False
    elif override == "npc":
        prefer = True

    provider = _resolve_llm_provider_name(prefer_npc=prefer)
    config = _provider_config(provider, prefer_npc=prefer)

    if provider == "mock":
        from webapp.llm_handler import MockProvider

        client = MockProvider()
        client.initialize({})
    elif provider == "openai":
        from webapp.llm_handler import OpenAIProvider

        client = OpenAIProvider()
        init_cfg = {"api_key": config.get("api_key"), "model": config.get("model")}
        if config.get("base_url"):
            init_cfg["base_url"] = config["base_url"]
        client.initialize(init_cfg)
    elif provider == "anthropic":
        from webapp.llm_handler import AnthropicProvider

        client = AnthropicProvider()
        client.initialize(
            {"api_key": config.get("api_key"), "model": config.get("model")}
        )
    elif provider in ("llama_cpp", "llama.cpp", "llamacpp"):
        from webapp.llm_handler import LlamaCppProvider

        client = LlamaCppProvider()
        client.initialize(config)
    else:
        from webapp.llm_handler import OllamaProvider

        client = OllamaProvider()
        client.initialize(config)

    def _send(messages: list[dict[str, str]]) -> str:
        return client.send_message(messages)

    return _send


def make_default_llm_sender() -> Callable[[list[dict[str, str]]], str]:
    """Backward-compatible alias for :func:`make_voice_profile_llm_sender`."""
    return make_voice_profile_llm_sender()
