"""Generate campaign NPC tokens and title/login backgrounds via Image Gen MCP."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml
from PIL import Image

from natural20.image_gen.mcp_client import (
    GeneratedImage,
    ImageGenMcpClient,
    ImageGenMcpError,
    default_mcp_url,
    save_pil,
)
from natural20.image_gen.prompts import (
    BACKGROUND_NEGATIVE,
    TOKEN_NEGATIVE,
    campaign_asset_mood,
    campaign_theme_blurb,
    character_portrait_prompt,
    character_selection_background_prompt,
    fit_clip_prompt,
    login_background_prompt,
    npc_scene_portrait_prompt,
    npc_token_prompt,
    npc_visual_description,
)
from natural20.image_gen.tokens import make_circular_token
from natural20.yaml_loader import load_yaml


GenerateFn = Callable[..., GeneratedImage]


@dataclass
class AssetJobResult:
    kind: str
    key: str
    output_path: Path
    skipped: bool = False
    reason: str = ""
    error: str = ""


@dataclass
class CampaignAssetReport:
    results: list[AssetJobResult] = field(default_factory=list)

    @property
    def errors(self) -> list[AssetJobResult]:
        return [r for r in self.results if r.error]

    @property
    def written(self) -> list[AssetJobResult]:
        return [r for r in self.results if not r.skipped and not r.error]


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower())
    return text.strip("_") or "asset"


def _race_label(raw: Any) -> str | None:
    if isinstance(raw, list) and raw:
        return str(raw[0])
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def load_campaign_meta(campaign: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    game_path = campaign / "game.yml"
    if game_path.is_file():
        data = load_yaml(game_path, campaign_root=campaign) or {}
        if isinstance(data, dict):
            meta.update(data)
    index_path = campaign / "index.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if isinstance(index, dict):
            # index title/login fields win for presentation assets
            for key in ("title", "login_background", "character_selection_background", "selectable_characters"):
                if key in index:
                    meta[key] = index[key]
            meta["_index"] = index
    return meta


def ensure_pc_image_fields(
    campaign: Path,
    sheet_rel: str,
    *,
    profile_image: str,
    token_image: str,
) -> None:
    path = campaign / sheet_rel
    if not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return
    changed = False
    if data.get("profile_image") != profile_image:
        data["profile_image"] = profile_image
        changed = True
    if data.get("token_image") != token_image:
        data["token_image"] = token_image
        changed = True
    if changed:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def selectable_character_sheet(campaign: Path, entry: dict[str, Any]) -> dict[str, Any]:
    sheet_rel = str(entry.get("sheet") or "").strip()
    if not sheet_rel:
        return {}
    data = load_yaml(campaign / sheet_rel, campaign_root=campaign) or {}
    return data if isinstance(data, dict) else {}


def selectable_character_entity_uid(entry: dict[str, Any]) -> str:
    overrides = entry.get("overrides") or {}
    if isinstance(overrides, dict) and overrides.get("entity_uid"):
        return str(overrides["entity_uid"])
    return str(entry.get("name") or "character")


def selectable_character_class_label(sheet: dict[str, Any]) -> str | None:
    classes = sheet.get("classes")
    if not isinstance(classes, dict) or not classes:
        return None
    return next(iter(classes.keys()), None)


def selectable_character_description(entry: dict[str, Any], sheet: dict[str, Any]) -> str:
    for source in (entry.get("description"), sheet.get("description"), sheet.get("outward_appearance")):
        text = str(source or "").strip()
        if text:
            return text
    return ""


def selectable_character_display_name(entry: dict[str, Any], sheet: dict[str, Any]) -> str:
    return str(sheet.get("name") or entry.get("name") or "character")


def discover_npc_defs(campaign: Path) -> list[dict[str, Any]]:
    npc_dir = campaign / "npcs"
    if not npc_dir.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for path in sorted(npc_dir.glob("*.yml")):
        data = load_yaml(path, campaign_root=campaign) or {}
        if not isinstance(data, dict):
            continue
        # Support both single-NPC files and multi-entry maps files.
        if "kind" in data or "description" in data:
            entry = dict(data)
            entry["_source"] = str(path.relative_to(campaign))
            entry["_file_stem"] = path.stem
            found.append(entry)
            continue
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            if not (value.get("kind") or value.get("token") or value.get("max_hp")):
                continue
            entry = dict(value)
            entry.setdefault("kind", key)
            entry["_source"] = str(path.relative_to(campaign))
            entry["_file_stem"] = path.stem
            entry["_entry_key"] = key
            found.append(entry)
    return found


def token_filename_for_npc(npc: dict[str, Any]) -> str:
    kind = npc.get("kind") or npc.get("_file_stem") or npc.get("name") or "npc"
    return f"token_{_slug(str(kind))}.png"


def portrait_filename_for_npc(npc: dict[str, Any]) -> str:
    kind = npc.get("kind") or npc.get("_file_stem") or npc.get("name") or "npc"
    return f"portraits/portrait_{_slug(str(kind))}.jpg"


def ensure_npc_profile_image_field(campaign: Path, npc: dict[str, Any], filename: str) -> None:
    source = npc.get("_source")
    if not source:
        return
    path = campaign / source
    if not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return
    entry_key = npc.get("_entry_key")
    target = data[entry_key] if entry_key and isinstance(data.get(entry_key), dict) else data
    if not isinstance(target, dict):
        return
    if target.get("profile_image") == filename:
        return
    target["profile_image"] = filename
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def ensure_npc_token_image_field(campaign: Path, npc: dict[str, Any], filename: str) -> None:
    """Write token_image onto the NPC YAML when missing."""
    source = npc.get("_source")
    if not source:
        return
    path = campaign / source
    if not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return
    entry_key = npc.get("_entry_key")
    target = data[entry_key] if entry_key and isinstance(data.get(entry_key), dict) else data
    if not isinstance(target, dict):
        return
    if target.get("token_image") == filename:
        return
    target["token_image"] = filename
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def generate_campaign_assets(
    campaign: Path | str,
    *,
    mcp_url: str | None = None,
    tokens: bool = True,
    background: bool = True,
    portraits: bool = False,
    force: bool = False,
    update_yaml: bool = True,
    token_size: int = 256,
    dry_run: bool = False,
    only: Iterable[str] | None = None,
    generator: GenerateFn | None = None,
    client: ImageGenMcpClient | None = None,
    quality: str = "medium",
    model: str | None = None,
) -> CampaignAssetReport:
    campaign = Path(campaign).resolve()
    meta = load_campaign_meta(campaign)
    theme = campaign_asset_mood(meta)
    title = meta.get("title") or meta.get("name") or campaign.name
    if isinstance(title, list):
        title = " ".join(str(p) for p in title)
    description = str(meta.get("description") or "")
    only_set = {x.lower() for x in only} if only else None

    owns_client = False
    if generator is None:
        if client is None:
            client = ImageGenMcpClient(mcp_url or default_mcp_url())
            owns_client = True
            client.initialize()

        def _gen(**kwargs):
            if model and "model" not in kwargs:
                kwargs["model"] = model
            return client.generate_image(**kwargs)

        generator = _gen

    report = CampaignAssetReport()
    assets_dir = campaign / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    try:
        if tokens:
            for npc in discover_npc_defs(campaign):
                key = str(npc.get("kind") or npc.get("_file_stem"))
                if only_set and key.lower() not in only_set and _slug(key) not in only_set:
                    continue
                filename = token_filename_for_npc(npc)
                out = assets_dir / filename
                if out.is_file() and not force:
                    report.results.append(
                        AssetJobResult("token", key, out, skipped=True, reason="exists")
                    )
                    if update_yaml and not dry_run:
                        ensure_npc_token_image_field(campaign, npc, filename)
                    continue
                portrait_scene = str(npc.get("portrait_scene") or "").strip()
                custom_prompt = str(npc.get("image_prompt") or "").strip()
                if custom_prompt:
                    custom_prompt = fit_clip_prompt(custom_prompt)
                if dry_run:
                    visual_desc = npc_visual_description(npc)
                    preview = custom_prompt or (
                        npc_scene_portrait_prompt(
                            name=str(npc.get("kind") or key),
                            kind=str(npc.get("kind") or key),
                            description=visual_desc,
                            race=_race_label(npc.get("race")),
                            scene=portrait_scene or "town",
                            theme=theme,
                        )[:80]
                        if portrait_scene
                        else npc_token_prompt(
                            name=str(npc.get("kind") or key),
                            kind=str(npc.get("kind") or key),
                            description=visual_desc,
                            race=_race_label(npc.get("race")),
                            alignment=str(npc.get("alignment") or "") or None,
                            theme=theme,
                        )[:80]
                    )
                    report.results.append(
                        AssetJobResult("token", key, out, skipped=True, reason=f"dry-run: {preview}")
                    )
                    continue
                try:
                    visual_desc = npc_visual_description(npc)
                    if portrait_scene:
                        prompt = custom_prompt or npc_scene_portrait_prompt(
                            name=str(npc.get("kind") or key),
                            kind=str(npc.get("kind") or key),
                            description=visual_desc,
                            race=_race_label(npc.get("race")),
                            scene=portrait_scene,
                            theme=theme,
                        )
                        generated = generator(
                            prompt=prompt,
                            size="896x1152",
                            quality=quality,
                            negative_prompt=TOKEN_NEGATIVE,
                            output_format="jpeg",
                        )
                        portrait_rel = portrait_filename_for_npc(npc)
                        portrait_out = assets_dir / portrait_rel
                        portrait_out.parent.mkdir(parents=True, exist_ok=True)
                        save_pil(generated.image.convert("RGB"), portrait_out, format="JPEG")
                        token = make_circular_token(generated.image, size=token_size)
                        save_pil(token, out)
                        if update_yaml:
                            ensure_npc_token_image_field(campaign, npc, filename)
                            ensure_npc_profile_image_field(campaign, npc, portrait_rel)
                        report.results.append(AssetJobResult("portrait", key, portrait_out))
                        report.results.append(AssetJobResult("token", key, out))
                        continue

                    prompt = custom_prompt or npc_token_prompt(
                        name=str(npc.get("kind") or key),
                        kind=str(npc.get("kind") or key),
                        description=visual_desc,
                        race=_race_label(npc.get("race")),
                        alignment=str(npc.get("alignment") or "") or None,
                        theme=theme,
                    )
                    generated = generator(
                        prompt=prompt,
                        size="1024x1024",
                        quality=quality,
                        negative_prompt=TOKEN_NEGATIVE,
                        output_format="png",
                    )
                    token = make_circular_token(generated.image, size=token_size)
                    save_pil(token, out)
                    if update_yaml:
                        ensure_npc_token_image_field(campaign, npc, filename)
                    report.results.append(AssetJobResult("token", key, out))
                except Exception as exc:  # noqa: BLE001 — collect per-asset failures
                    report.results.append(
                        AssetJobResult("token", key, out, error=str(exc))
                    )

        if background:
            background_jobs: list[tuple[str, str, Callable[..., str]]] = [
                (
                    "login",
                    str(meta.get("login_background") or f"{_slug(str(title))}_title.png"),
                    login_background_prompt,
                ),
            ]
            char_select = meta.get("character_selection_background")
            if char_select:
                background_jobs.append(
                    (
                        "character_selection",
                        str(char_select),
                        character_selection_background_prompt,
                    )
                )

            for job_key, asset_name, prompt_builder in background_jobs:
                out = assets_dir / Path(asset_name).name
                if out.is_file() and not force:
                    report.results.append(
                        AssetJobResult("background", job_key, out, skipped=True, reason="exists")
                    )
                    continue
                prompt = prompt_builder(
                    title=str(title),
                    description=description,
                    theme_keywords=theme,
                )
                if dry_run:
                    report.results.append(
                        AssetJobResult(
                            "background",
                            job_key,
                            out,
                            skipped=True,
                            reason=f"dry-run: {prompt[:80]}",
                        )
                    )
                    continue
                try:
                    # Prefer explicit WxH for FLUX; aspect_ratio is Qwen-only.
                    bg_size = "1280x720"
                    if out.suffix.lower() in {".jpg", ".jpeg"}:
                        out_fmt = "jpeg"
                    else:
                        out_fmt = "png"
                    generated = generator(
                        prompt=prompt,
                        size=bg_size,
                        quality=quality,
                        negative_prompt=BACKGROUND_NEGATIVE,
                        output_format=out_fmt,
                    )
                    image = generated.image
                    if out.suffix.lower() in {".jpg", ".jpeg"}:
                        save_pil(image.convert("RGB"), out, format="JPEG")
                    else:
                        save_pil(image, out)
                    report.results.append(AssetJobResult("background", job_key, out))
                except Exception as exc:  # noqa: BLE001
                    report.results.append(
                        AssetJobResult("background", job_key, out, error=str(exc))
                    )

        if portraits:
            for entry in meta.get("selectable_characters") or []:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "character")
                if only_set and name.lower() not in only_set:
                    entity_uid = selectable_character_entity_uid(entry)
                    if entity_uid.lower() not in only_set and _slug(entity_uid) not in only_set:
                        continue
                sheet = selectable_character_sheet(campaign, entry)
                display_name = selectable_character_display_name(entry, sheet)
                entity_uid = selectable_character_entity_uid(entry)
                rel = str(entry.get("file") or f"characters/{name}.png")
                profile_out = campaign / "assets" / rel
                token_out = assets_dir / f"token_{_slug(entity_uid)}.png"
                profile_out.parent.mkdir(parents=True, exist_ok=True)
                portrait_exists = profile_out.is_file()
                token_exists = token_out.is_file()
                if portrait_exists and token_exists and not force:
                    report.results.append(
                        AssetJobResult("portrait", name, profile_out, skipped=True, reason="exists")
                    )
                    if update_yaml:
                        ensure_pc_image_fields(
                            campaign,
                            str(entry.get("sheet") or ""),
                            profile_image=rel,
                            token_image=token_out.name,
                        )
                    continue
                prompt = character_portrait_prompt(
                    name=display_name,
                    description=selectable_character_description(entry, sheet),
                    race=_race_label(sheet.get("race")),
                    character_class=selectable_character_class_label(sheet),
                    theme=theme,
                )
                if dry_run:
                    report.results.append(
                        AssetJobResult(
                            "portrait",
                            name,
                            profile_out,
                            skipped=True,
                            reason=f"dry-run: {prompt[:80]}",
                        )
                    )
                    continue
                try:
                    generated = generator(
                        prompt=prompt,
                        size="896x1152",
                        quality=quality,
                        negative_prompt=TOKEN_NEGATIVE,
                        output_format="png",
                    )
                    save_pil(generated.image, profile_out)
                    token = make_circular_token(generated.image, size=token_size)
                    save_pil(token, token_out)
                    if update_yaml and entry.get("sheet"):
                        ensure_pc_image_fields(
                            campaign,
                            str(entry["sheet"]),
                            profile_image=rel,
                            token_image=token_out.name,
                        )
                    report.results.append(AssetJobResult("portrait", name, profile_out))
                    report.results.append(AssetJobResult("token", entity_uid, token_out))
                except Exception as exc:  # noqa: BLE001
                    report.results.append(
                        AssetJobResult("portrait", name, profile_out, error=str(exc))
                    )
    finally:
        if owns_client and client is not None:
            client.close()

    return report


def status_probe(mcp_url: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
    """Return a small readiness dict for CLI / agents."""
    client = ImageGenMcpClient(mcp_url or default_mcp_url(), timeout=timeout)
    try:
        info = client.initialize()
        try:
            status = client.check_server_status()
        except ImageGenMcpError as exc:
            status = {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
        return {
            "ok": not bool(status.get("isError")),
            "url": client.url,
            "server": (info.get("serverInfo") or {}),
            "status": status,
        }
    except ImageGenMcpError as exc:
        return {
            "ok": False,
            "url": client.url,
            "server": {},
            "status": {"isError": True, "content": [{"type": "text", "text": str(exc)}]},
        }
    finally:
        client.close()
