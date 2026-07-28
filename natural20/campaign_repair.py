"""LLM-assisted campaign repair for validation findings."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from natural20.campaign_validator.catalog import CampaignCatalog
from natural20.campaign_validator.report import ValidationIssue, ValidationReport


@dataclass
class RepairProposal:
    issue: ValidationIssue
    action: str
    target_path: Path
    original_text: str | None
    new_text: str
    summary: str


@dataclass
class RepairOptions:
    apply: bool = False
    dry_run: bool = True
    backup: bool = True
    use_llm: bool = True
    max_repairs: int = 20


def repair_campaign(
    campaign: Path | str,
    report: ValidationReport,
    options: RepairOptions | None = None,
) -> list[RepairProposal]:
    """Attempt automated repairs for repairable validation issues."""
    opts = options or RepairOptions()
    campaign_path = Path(campaign).expanduser().resolve()
    catalog = CampaignCatalog(campaign_path)
    proposals: list[RepairProposal] = []

    for issue in report.repairable_issues[: opts.max_repairs]:
        proposal = _repair_issue(campaign_path, catalog, issue, opts)
        if proposal is not None:
            proposals.append(proposal)

    if opts.apply and not opts.dry_run:
        _apply_proposals(campaign_path, proposals, backup=opts.backup)

    return proposals


def _repair_issue(
    campaign: Path,
    catalog: CampaignCatalog,
    issue: ValidationIssue,
    options: RepairOptions,
) -> RepairProposal | None:
    if issue.code == "missing_item":
        return _repair_missing_definition(
            campaign,
            issue,
            options,
            target_file=campaign / "items" / "equipment.yml",
            catalog_keys=sorted(set(catalog.equipment) | set(catalog.weapons) | set(catalog.magic_items)),
            definition_kind="equipment item",
        )
    if issue.code == "missing_spell":
        return _repair_missing_definition(
            campaign,
            issue,
            options,
            target_file=campaign / "items" / "spells.yml",
            catalog_keys=sorted(catalog.spells),
            definition_kind="spell",
        )
    if issue.code == "missing_npc":
        return _repair_missing_definition(
            campaign,
            issue,
            options,
            target_file=campaign / "npcs" / f"{issue.context.get('npc_type', 'custom_npc')}.yml",
            catalog_keys=sorted(set(catalog.npcs.values())),
            definition_kind="npc",
            single_file=True,
        )
    if issue.code == "missing_object":
        return _repair_missing_definition(
            campaign,
            issue,
            options,
            target_file=campaign / "items" / "objects.yml",
            catalog_keys=sorted(catalog.objects),
            definition_kind="map object",
        )
    if issue.code in {"yaml_format_tabs", "yaml_format_trailing_ws", "yaml_format_final_newline"}:
        return _repair_formatting(campaign, issue)
    if issue.code == "yaml_syntax" and issue.path:
        return _repair_yaml_syntax(campaign, issue, options)
    return _repair_reference_typo(campaign, issue)


def _repair_reference_typo(campaign: Path, issue: ValidationIssue) -> RepairProposal | None:
    suggestions = issue.context.get("suggestions") or []
    if not suggestions:
        return None
    replacement = suggestions[0]
    rel_path = issue.path
    if not rel_path:
        return None
    path = campaign / rel_path
    if not path.is_file():
        return None
    original = path.read_text(encoding="utf-8")
    old_token = (
        issue.context.get("item")
        or issue.context.get("spell")
        or issue.context.get("npc_type")
        or issue.context.get("object_type")
    )
    if not old_token or old_token not in original:
        return None
    new_text = original.replace(old_token, replacement, 1)
    return RepairProposal(
        issue=issue,
        action="replace_reference",
        target_path=path,
        original_text=original,
        new_text=new_text,
        summary=f"Replace {old_token!r} with {replacement!r} in {rel_path}",
    )


def _repair_formatting(campaign: Path, issue: ValidationIssue) -> RepairProposal | None:
    rel_path = issue.path
    if not rel_path:
        return None
    path = campaign / rel_path
    if not path.is_file():
        return None
    original = path.read_text(encoding="utf-8")
    updated = original.replace("\t", "  ")
    lines = [line.rstrip() for line in updated.splitlines()]
    updated = "\n".join(lines)
    if updated and not updated.endswith("\n"):
        updated += "\n"
    if updated == original:
        return None
    return RepairProposal(
        issue=issue,
        action="format_yaml",
        target_path=path,
        original_text=original,
        new_text=updated,
        summary=f"Normalize YAML formatting in {rel_path}",
    )


def _repair_yaml_syntax(
    campaign: Path,
    issue: ValidationIssue,
    options: RepairOptions,
) -> RepairProposal | None:
    rel_path = issue.path
    if not rel_path:
        return None
    path = campaign / rel_path
    if not path.is_file():
        return None
    original = path.read_text(encoding="utf-8")
    if options.use_llm:
        fixed = _llm_fix_yaml(original, issue.message)
        if fixed and fixed != original:
            return RepairProposal(
                issue=issue,
                action="fix_yaml_syntax",
                target_path=path,
                original_text=original,
                new_text=fixed,
                summary=f"LLM-repaired YAML syntax in {rel_path}",
            )
    return None


def _repair_missing_definition(
    campaign: Path,
    issue: ValidationIssue,
    options: RepairOptions,
    *,
    target_file: Path,
    catalog_keys: list[str],
    definition_kind: str,
    single_file: bool = False,
) -> RepairProposal | None:
    key = (
        issue.context.get("item")
        or issue.context.get("spell")
        or issue.context.get("npc_type")
        or issue.context.get("object_type")
    )
    if not key:
        return None

    suggestions = issue.context.get("suggestions") or []
    if suggestions and not options.use_llm:
        return _repair_reference_typo(campaign, issue)

    if single_file:
        if target_file.is_file():
            original = target_file.read_text(encoding="utf-8")
        else:
            original = ""
            target_file.parent.mkdir(parents=True, exist_ok=True)
        if options.use_llm:
            snippet = _llm_generate_definition(
                definition_kind,
                key,
                issue=issue,
                examples=_example_entries(catalog_keys, target_file if target_file.is_file() else None),
            )
            if not snippet:
                return None
            new_text = f"{original.rstrip()}\n\n{snippet.strip()}\n" if original.strip() else f"{snippet.strip()}\n"
            return RepairProposal(
                issue=issue,
                action="create_definition",
                target_path=target_file,
                original_text=original or None,
                new_text=new_text,
                summary=f"Create {definition_kind} definition for {key!r} in {target_file.relative_to(campaign)}",
            )
        return None

    if not target_file.is_file():
        target_file.parent.mkdir(parents=True, exist_ok=True)
        original = ""
        existing: dict[str, Any] = {}
    else:
        original = target_file.read_text(encoding="utf-8")
        existing = yaml.safe_load(original) or {}
        if not isinstance(existing, dict):
            existing = {}

    if key in existing:
        return _repair_reference_typo(campaign, issue)

    if options.use_llm:
        snippet = _llm_generate_definition(
            definition_kind,
            key,
            issue=issue,
            examples=_example_entries(catalog_keys, target_file if target_file.is_file() else None),
        )
        if snippet:
            new_text = f"{original.rstrip()}\n\n{snippet.strip()}\n" if original.strip() else f"{snippet.strip()}\n"
            return RepairProposal(
                issue=issue,
                action="append_definition",
                target_path=target_file,
                original_text=original or None,
                new_text=new_text,
                summary=f"Append {definition_kind} definition for {key!r} to {target_file.relative_to(campaign)}",
            )

    stub = _stub_definition(definition_kind, key)
    merged = dict(existing)
    merged[key] = stub
    new_text = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True)
    return RepairProposal(
        issue=issue,
        action="append_stub",
        target_path=target_file,
        original_text=original or None,
        new_text=new_text,
        summary=f"Append stub {definition_kind} for {key!r} to {target_file.relative_to(campaign)}",
    )


def _example_entries(catalog_keys: list[str], path: Path | None, *, limit: int = 2) -> str:
    if not path or not path.is_file() or not catalog_keys:
        return ""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return ""
    chunks: list[str] = []
    for key in catalog_keys[:limit]:
        if key in data:
            chunks.append(yaml.safe_dump({key: data[key]}, sort_keys=False, allow_unicode=True).strip())
    return "\n\n".join(chunks)


def _stub_definition(kind: str, key: str) -> dict[str, Any]:
    label = key.replace("_", " ").title()
    if kind == "spell":
        return {
            "label": label,
            "name": label,
            "level": 0,
            "school": "evocation",
            "casting_time": "1:action",
            "range": 30,
            "duration": "instant",
            "components": ["verbal", "somatic"],
            "description": f"TODO: define {label}.",
            "type": "utility",
            "spell_list_classes": ["Wizard"],
        }
    if kind == "npc":
        return {
            "kind": label.replace(" ", ""),
            "description": f"TODO: define {label}.",
            "size": "medium",
            "max_hp": 10,
            "default_ac": 10,
            "speed": 30,
        }
    if kind == "map object":
        return {
            "name": label,
            "type": "interactable",
            "description": f"TODO: define {label}.",
        }
    return {
        "name": label,
        "type": "gear",
        "description": f"TODO: define {label}.",
    }


def _llm_handler():
    import sys

    repo_root = Path(__file__).resolve().parent.parent
    webapp_path = repo_root / "webapp"
    if str(webapp_path) not in sys.path:
        sys.path.insert(0, str(webapp_path))
    from blueprints.helpers.llm_init import configure_llm_handler_from_environment
    from llm_handler import LLMHandler

    handler = LLMHandler()
    if not configure_llm_handler_from_environment(handler):
        return None
    return handler


def _llm_complete(system_prompt: str, user_prompt: str) -> str | None:
    handler = _llm_handler()
    if handler is None or handler.current_provider is None:
        return None
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    response = handler.current_provider.send_message(messages)
    return response.strip() if response else None


def _extract_yaml_block(text: str) -> str | None:
    fence = re.search(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidate = fence.group(1).strip() if fence else text.strip()
    try:
        parsed = yaml.safe_load(candidate)
    except yaml.YAMLError:
        return None
    if parsed is None:
        return None
    if isinstance(parsed, dict) and len(parsed) == 1:
        return yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True).strip()
    return yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True).strip()


def _llm_generate_definition(
    kind: str,
    key: str,
    *,
    issue: ValidationIssue,
    examples: str,
) -> str | None:
    system_prompt = (
        "You generate Natural20 campaign YAML definitions. "
        "Return only valid YAML for a single top-level key. "
        "Use snake_case keys, match existing Natural20 schema conventions, "
        "and do not invent unsupported engine fields."
    )
    user_prompt = (
        f"Create a minimal but valid Natural20 {kind} definition with top-level key {key!r}.\n"
        f"Validation issue: {issue.message}\n"
    )
    if examples:
        user_prompt += f"\nExamples from this campaign:\n```yaml\n{examples}\n```\n"
    user_prompt += "\nReturn only the YAML mapping."
    response = _llm_complete(system_prompt, user_prompt)
    if not response:
        return None
    return _extract_yaml_block(response)


def _llm_fix_yaml(original: str, error_message: str) -> str | None:
    system_prompt = (
        "You repair YAML syntax errors for Natural20 campaign files. "
        "Preserve semantics and formatting style where possible. "
        "Return only the full corrected YAML file."
    )
    user_prompt = (
        f"Fix this YAML file.\nError: {error_message}\n\n```yaml\n{original}\n```"
    )
    response = _llm_complete(system_prompt, user_prompt)
    if not response:
        return None
    fixed = _extract_yaml_block(response) or response
    try:
        yaml.safe_load(fixed)
    except yaml.YAMLError:
        return None
    if not fixed.endswith("\n"):
        fixed += "\n"
    return fixed


def _apply_proposals(campaign: Path, proposals: list[RepairProposal], *, backup: bool) -> None:
    backup_dir = campaign / ".campaign_validator_backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
    for proposal in proposals:
        path = proposal.target_path
        if backup and path.is_file():
            backup_dir.mkdir(parents=True, exist_ok=True)
            rel = path.relative_to(campaign)
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(proposal.new_text, encoding="utf-8")


def proposals_to_json(proposals: list[RepairProposal]) -> list[dict[str, Any]]:
    return [
        {
            "action": proposal.action,
            "target": str(proposal.target_path),
            "summary": proposal.summary,
            "issue": proposal.issue.to_dict(),
        }
        for proposal in proposals
    ]
