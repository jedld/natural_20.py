#!/usr/bin/env python3
"""Audit locale keys, add missing entries, and optionally fill/translate with an LLM."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import i18n
import requests

from natural20.utils.localization import (
    discover_locale_files,
    ensure_default_locale_paths,
    get_locale_value,
    is_locale_key,
    load_locale_document,
    locale_language_name,
    merge_missing_locale_entries,
    missing_locale_keys,
    save_locale_document,
    scan_locale_key_references,
    set_locale_value,
)


def _ollama_generate(prompt: str, *, model: Optional[str] = None, base_url: Optional[str] = None) -> str:
    base_url = (base_url or os.getenv('OLLAMA_BASE_URL') or 'http://localhost:11434').rstrip('/')
    model = model or os.getenv('OLLAMA_MODEL') or os.getenv('NPC_MODEL') or 'llama3.2'
    response = requests.post(
        f'{base_url}/api/generate',
        json={'model': model, 'prompt': prompt, 'stream': False},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get('response') or '').strip()


def _openai_generate(prompt: str, *, model: Optional[str] = None) -> str:
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY is not set')
    model = model or os.getenv('OPENAI_MODEL') or 'gpt-4o-mini'
    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'You write concise UI strings for a D&D 5e virtual tabletop.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.2,
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload['choices'][0]['message']['content']).strip()


def _llm_generate(prompt: str, *, provider: Optional[str] = None) -> str:
    provider = (provider or os.getenv('LLM_PROVIDER') or 'ollama').lower()
    if provider == 'openai':
        return _openai_generate(prompt)
    return _ollama_generate(prompt)


def _context_snippet(references: Dict[str, List], key: str, limit: int = 3) -> str:
    lines = references.get(key) or []
    chunks = []
    for rel_path, line_no, line_text in lines[:limit]:
        chunks.append(f'{rel_path}:{line_no}: {line_text}')
    return '\n'.join(chunks)


def _infer_english_label(key: str, references: Dict[str, List], llm: bool, provider: Optional[str]) -> str:
    if not llm:
        return key.split('.')[-1].replace('_', ' ').title()

    context = _context_snippet(references, key)
    prompt = (
        'Write a short English UI label (max 8 words) for this locale key in a D&D 5e game.\n'
        f'Key: {key}\n'
        f'Code context:\n{context or "(no context)"}\n'
        'Return only the label text, no quotes or explanation.'
    )
    text = _llm_generate(prompt, provider=provider)
    return text.strip().strip('"').strip("'")


def _translate_label(
    english_text: str,
    *,
    target_locale: str,
    key: str,
    llm: bool,
    provider: Optional[str],
) -> str:
    if target_locale.lower() == 'en':
        return english_text
    if not llm:
        return english_text

    language = locale_language_name(target_locale)
    prompt = (
        f'Translate this D&D 5e UI string to {language}. Keep it concise.\n'
        f'Locale key: {key}\n'
        f'English: {english_text}\n'
        'Return only the translated text.'
    )
    text = _llm_generate(prompt, provider=provider)
    return text.strip().strip('"').strip("'")


def audit_locale_file(
    locale_path: Path,
    references: Dict[str, List],
    *,
    write: bool,
    llm_fill: bool,
    translate_missing: bool,
    provider: Optional[str],
) -> Dict[str, Any]:
    locale_code, tree = load_locale_document(locale_path)
    ensure_default_locale_paths()
    i18n.set('locale', locale_code)
    i18n.set('fallback', 'en')

    missing = missing_locale_keys(references.keys(), tree)
    report: Dict[str, Any] = {
        'path': str(locale_path),
        'locale': locale_code,
        'missing': missing,
        'added': 0,
        'translated': 0,
    }
    if not missing and not translate_missing:
        return report

    english_path = locale_path.with_name('en.yml')
    english_tree: Dict[str, Any] = {}
    if english_path.is_file() and locale_code != 'en':
        _, english_tree = load_locale_document(english_path)

    entries: Dict[str, str] = {}
    for key in missing:
        english_value = get_locale_value(english_tree, key) if english_tree else None
        if english_value is None and locale_code == 'en':
            english_value = _infer_english_label(key, references, llm_fill, provider)
        elif english_value is None:
            english_value = _infer_english_label(key, references, llm_fill, provider)

        if locale_code == 'en':
            entries[key] = english_value
        elif translate_missing:
            entries[key] = _translate_label(
                str(english_value),
                target_locale=locale_code,
                key=key,
                llm=llm_fill,
                provider=provider,
            )
            report['translated'] += 1
        else:
            entries[key] = str(english_value)

    if write and entries:
        result = merge_missing_locale_entries(tree, entries)
        report['added'] = result['added']
        save_locale_document(locale_path, locale_code, tree)

    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Audit and fill locale YAML files.')
    parser.add_argument('--campaign', default=None, help='Campaign directory (e.g. user_levels/wild_sheep_chase)')
    parser.add_argument('--locale-file', default=None, help='Specific locale file to update')
    parser.add_argument('--write', action='store_true', help='Write missing keys into locale files')
    parser.add_argument('--llm-fill', action='store_true', help='Use an LLM to infer English labels and translations')
    parser.add_argument(
        '--translate-missing',
        action='store_true',
        help='For non-English locale files, translate missing keys from English',
    )
    parser.add_argument('--provider', default=None, help='LLM provider (ollama|openai)')
    parser.add_argument('--json', action='store_true', help='Emit machine-readable report')
    args = parser.parse_args(argv)

    campaign_root = Path(args.campaign).resolve() if args.campaign else None
    references = scan_locale_key_references(REPO_ROOT)

    if args.locale_file:
        locale_files = [Path(args.locale_file).resolve()]
    else:
        locale_files = discover_locale_files(REPO_ROOT, campaign_root=campaign_root)

    reports = [
        audit_locale_file(
            path,
            references,
            write=args.write,
            llm_fill=args.llm_fill,
            translate_missing=args.translate_missing,
            provider=args.provider,
        )
        for path in locale_files
    ]

    if args.json:
        print(json.dumps(reports, indent=2))
        return 0

    total_missing = 0
    total_added = 0
    for report in reports:
        missing = report['missing']
        total_missing += len(missing)
        total_added += int(report.get('added') or 0)
        print(f"{report['path']} [{report['locale']}]: {len(missing)} missing")
        for key in missing[:20]:
            print(f"  - {key}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
        if report.get('added'):
            print(f"  added {report['added']} entries")

    print(f"\nScanned {len(references)} referenced keys across {len(locale_files)} locale file(s).")
    print(f"Missing: {total_missing}; added: {total_added}")
    if total_missing and not args.write:
        print('Re-run with --write to add placeholders, or --write --llm-fill for LLM-generated labels.')
    return 1 if total_missing and not args.write else 0


if __name__ == '__main__':
    raise SystemExit(main())
