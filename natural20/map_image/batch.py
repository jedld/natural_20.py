"""Batch rendering of missing campaign map background assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from natural20.map_image.assets import resolve_asset_path
from natural20.map_image.grid import load_map_grid
from natural20.map_image.renderer import render_map_image
from natural20.yaml_loader import load_yaml

DEFAULT_BATCH_LAYERS = ("base", "objects", "entities")


@dataclass(frozen=True)
class MapAssetJob:
    """A map that needs (or will receive) a background image asset."""

    map_id: str
    yaml_path: Path
    background_image: str | None
    expected_asset_path: Path
    asset_exists: bool
    reason: str

    @property
    def needs_render(self) -> bool:
        return not self.asset_exists


def _normalize_map_path(campaign: Path, rel: str) -> Path:
    rel_path = Path(rel)
    if rel_path.suffix != ".yml":
        rel_path = rel_path.with_suffix(".yml")
    if rel_path.parts[0] == "maps":
        candidate = campaign / rel_path
    else:
        candidate = campaign / "maps" / rel_path.name
    if candidate.is_file():
        return candidate.resolve()
    return (campaign / rel_path).resolve()


def discover_campaign_maps(
    campaign_root: str | Path,
    *,
    include_unlisted: bool = False,
) -> dict[str, Path]:
    """Return map_id -> absolute YAML path for a campaign."""
    campaign = Path(campaign_root).resolve()
    discovered: dict[str, Path] = {}

    game_path = campaign / "game.yml"
    if game_path.is_file():
        game = load_yaml(game_path, campaign_root=campaign)
        if isinstance(game, dict):
            for map_id, rel in (game.get("maps") or {}).items():
                if not isinstance(rel, str):
                    continue
                path = _normalize_map_path(campaign, rel)
                if path.is_file():
                    discovered[str(map_id)] = path

    if include_unlisted:
        maps_dir = campaign / "maps"
        if maps_dir.is_dir():
            for yml_path in sorted(maps_dir.glob("*.yml")):
                if yml_path.stem.lower() in {"monsters", "npcs", "encounters"}:
                    continue
                discovered.setdefault(yml_path.stem, yml_path.resolve())

    return discovered


def resolve_background_asset_path(
    campaign_root: Path,
    background_image: str,
) -> Path | None:
    """Return the first existing path for a background_image reference."""
    campaign = campaign_root.resolve()
    filename = Path(background_image).name
    candidates = [
        campaign / background_image,
        campaign / "assets" / background_image,
        campaign / "assets" / "maps" / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def default_background_filename(map_id: str) -> str:
    return f"{map_id}.png"


def default_asset_output_path(campaign_root: Path, map_id: str) -> Path:
    return campaign_root.resolve() / "assets" / "maps" / default_background_filename(map_id)


def _palette_for_map(map_id: str, properties: dict[str, Any]) -> str:
    from natural20.map_image.tiles import theme_for_name

    render_hints = properties.get("render") or (properties.get("map") or {}).get("render") or {}
    if isinstance(render_hints, dict) and render_hints.get("palette"):
        return str(render_hints["palette"])

    return theme_for_name(
        str(properties.get("name", "")),
        str(properties.get("description", "")),
        map_id=map_id,
    )


def _tile_size_for_campaign(campaign_root: Path, *, default: int = 64) -> int:
    index_path = campaign_root / "index.json"
    if not index_path.is_file():
        return default
    try:
        import json

        index = json.loads(index_path.read_text(encoding="utf-8"))
        tile_size = index.get("tile_size")
        if isinstance(tile_size, int) and tile_size > 0:
            return tile_size
    except Exception:
        pass
    return default


def find_maps_needing_assets(
    campaign_root: str | Path,
    *,
    include_without_background: bool = True,
    include_unlisted: bool = False,
) -> list[MapAssetJob]:
    """List maps whose background asset is missing or unset."""
    campaign = Path(campaign_root).resolve()
    jobs: list[MapAssetJob] = []

    for map_id, yaml_path in sorted(
        discover_campaign_maps(campaign, include_unlisted=include_unlisted).items()
    ):
        if not yaml_path.is_file():
            continue
        properties = load_yaml(yaml_path, campaign_root=campaign)
        if not isinstance(properties, dict):
            continue

        background_image = properties.get("background_image")
        if isinstance(background_image, str) and background_image.strip():
            background_image = background_image.strip()
            existing = resolve_background_asset_path(campaign, background_image)
            expected = existing or (campaign / "assets" / "maps" / Path(background_image).name)
            jobs.append(
                MapAssetJob(
                    map_id=map_id,
                    yaml_path=yaml_path,
                    background_image=background_image,
                    expected_asset_path=expected,
                    asset_exists=existing is not None,
                    reason="referenced asset missing" if existing is None else "asset present",
                )
            )
            continue

        if not include_without_background:
            continue

        filename = default_background_filename(map_id)
        expected = default_asset_output_path(campaign, map_id)
        exists = expected.is_file()
        jobs.append(
            MapAssetJob(
                map_id=map_id,
                yaml_path=yaml_path,
                background_image=None,
                expected_asset_path=expected,
                asset_exists=exists,
                reason="no background_image set" if not exists else "default asset present",
            )
        )

    return jobs


def update_map_background_reference(
    yaml_path: Path,
    background_image: str,
    *,
    campaign_root: Path,
) -> None:
    """Set background_image on a map YAML file."""
    properties = load_yaml(yaml_path, campaign_root=campaign_root)
    if not isinstance(properties, dict):
        raise ValueError(f"Map YAML must be a mapping: {yaml_path}")
    properties["background_image"] = background_image
    with yaml_path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(properties, stream, sort_keys=False)


@dataclass
class BatchRenderResult:
    map_id: str
    output_path: Path
    updated_yaml: bool
    skipped: bool
    message: str


def batch_render_missing_map_assets(
    campaign_root: str | Path,
    *,
    tile_size: int | None = None,
    palette: str | None = None,
    layers: Iterable[str] | None = None,
    show_grid: bool = False,
    diffusion: str | None = None,
    diffusion_style: str = "fantasy battlemap",
    diffusion_quality: str = "medium",
    mcp_url: str | None = None,
    background_opacity: float = 1.0,
    update_yaml: bool = False,
    dry_run: bool = False,
    force: bool = False,
    include_without_background: bool = True,
    include_unlisted: bool = False,
) -> list[BatchRenderResult]:
    """Render PNG backgrounds for maps with missing assets."""
    campaign = Path(campaign_root).resolve()
    if tile_size is None:
        tile_size = _tile_size_for_campaign(campaign)
    layer_tuple = tuple(layers or DEFAULT_BATCH_LAYERS)

    results: list[BatchRenderResult] = []
    jobs = find_maps_needing_assets(
        campaign,
        include_without_background=include_without_background,
        include_unlisted=include_unlisted,
    )

    for job in jobs:
        if job.asset_exists and not force:
            results.append(
                BatchRenderResult(
                    map_id=job.map_id,
                    output_path=job.expected_asset_path,
                    updated_yaml=False,
                    skipped=True,
                    message=job.reason,
                )
            )
            continue

        output_path = job.expected_asset_path
        if job.background_image and not job.asset_exists:
            resolved = resolve_background_asset_path(campaign, job.background_image)
            if resolved is None:
                output_path = campaign / "assets" / "maps" / Path(job.background_image).name
            else:
                output_path = resolved

        if dry_run:
            results.append(
                BatchRenderResult(
                    map_id=job.map_id,
                    output_path=output_path,
                    updated_yaml=update_yaml,
                    skipped=False,
                    message=f"would render -> {output_path}",
                )
            )
            continue

        properties = load_yaml(job.yaml_path, campaign_root=campaign)
        map_palette = palette or _palette_for_map(job.map_id, properties if isinstance(properties, dict) else {})

        render_map_image(
            output=output_path,
            campaign=campaign,
            map_name=str(job.yaml_path.relative_to(campaign)),
            tile_size=tile_size,
            palette=map_palette,
            layers=layer_tuple,
            show_grid=show_grid,
            image_format="png",
            diffusion=diffusion,
            diffusion_style=diffusion_style,
            diffusion_quality=diffusion_quality,
            mcp_url=mcp_url,
            background_opacity=background_opacity,
            skip_background_image=True,
        )

        yaml_updated = False
        background_value = job.background_image or default_background_filename(job.map_id)
        if update_yaml and job.background_image is None:
            update_map_background_reference(
                job.yaml_path,
                background_value,
                campaign_root=campaign,
            )
            yaml_updated = True
        elif update_yaml and job.background_image and not job.asset_exists:
            # File now exists at output_path; ensure YAML references a basename the webapp expects.
            if Path(job.background_image).name != output_path.name:
                update_map_background_reference(
                    job.yaml_path,
                    output_path.name,
                    campaign_root=campaign,
                )
                yaml_updated = True

        results.append(
            BatchRenderResult(
                map_id=job.map_id,
                output_path=output_path.resolve(),
                updated_yaml=yaml_updated,
                skipped=False,
                message="rendered",
            )
        )

    return results
