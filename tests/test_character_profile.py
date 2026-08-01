"""Tests for D&D 5e character profile utilities."""
from __future__ import annotations

import random

from natural20.utils.character_profile import (
    extract_profile,
    merge_profile_into_mapping,
    randomize_profile,
    resolve_size,
    format_profile_for_llm,
    profile_from_form,
)


def test_extract_profile_flat_and_nested():
    props = {
        'alignment': 'neutral_good',
        'gender': 'Female',
        'personality_traits': 'I love mysteries.',
        'characteristics': {'eyes': 'green'},
    }
    profile = extract_profile(props)
    assert profile['alignment'] == 'neutral_good'
    assert profile['gender'] == 'Female'
    assert profile['personality_traits'] == 'I love mysteries.'
    assert profile['eyes'] == 'green'


def test_merge_profile_into_mapping_clears_empty():
    pc = {'name': 'Test', 'alignment': 'chaotic_good', 'age': '30'}
    merge_profile_into_mapping(pc, {'alignment': '', 'age': '25'})
    assert 'alignment' not in pc
    assert pc['age'] == '25'


def test_resolve_size_prefers_override_then_race():
    assert resolve_size({'size': 'small'}, {'size': 'medium'}) == 'small'
    assert resolve_size({}, {'size': 'small'}) == 'small'
    assert resolve_size({}, None) == 'medium'


def test_randomize_profile_uses_background_tables():
    rng = random.Random(0)
    profile = randomize_profile(background='sage', race_def={'size': 'medium'}, rng=rng)
    assert profile['personality_traits']
    assert profile['ideals']
    assert profile['bonds']
    assert profile['flaws']
    assert profile['alignment'] in {
        'lawful_good', 'neutral_good', 'chaotic_good',
        'lawful_neutral', 'true_neutral', 'chaotic_neutral',
        'lawful_evil', 'neutral_evil', 'chaotic_evil',
    }
    assert profile['eyes']
    assert profile['height']
    assert profile['weight']


def test_profile_from_form():
    form = {
        'alignment': 'lawful_good',
        'personality_traits': 'Brave.',
        'outward_appearance': '  ',
    }
    profile = profile_from_form(form)
    assert profile['alignment'] == 'lawful_good'
    assert profile['personality_traits'] == 'Brave.'
    assert 'outward_appearance' not in profile


def test_format_profile_for_llm():
    text = format_profile_for_llm({
        'alignment': 'true_neutral',
        'personality_traits': 'Quiet.',
        'backstory': 'Once upon a time.',
    })
    assert 'Alignment: true_neutral' in text
    assert 'Personality traits: Quiet.' in text
    assert 'Backstory: Once upon a time.' in text
