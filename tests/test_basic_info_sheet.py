"""Smoke-render the D&D 5e Basic Info character sheet layout."""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.outward_appearance import (
    explicit_outward_appearance,
    resolve_outward_appearance,
)
from webapp.blueprints.helpers.template_globals import ability_mod_str, format_languages


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATE_DIR = os.path.join(REPO_ROOT, 'n20-webapp', 'webapp', 'templates')


def _format_outward_appearance(entity):
    props = getattr(entity, 'properties', {}) or {}
    explicit = explicit_outward_appearance(props)
    resolved = resolve_outward_appearance(entity, session=getattr(entity, 'session', None))
    return {
        'explicit': explicit,
        'resolved': resolved,
        'is_derived': not bool(explicit),
    }


def _render_basic_info(entity, role=('dm',)):
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(['html']),
    )
    env.filters['mod_str'] = ability_mod_str
    env.globals.update({
        'format_languages': format_languages,
        'format_outward_appearance': _format_outward_appearance,
        'can_rest_for': lambda _uid: True,
        'character_description_suppressed_for': lambda entity, viewer_is_dm=False: False,
        't': lambda key: key,
    })
    return env.get_template('_basic_info_sheet.html').render(
        entity=entity,
        battle=None,
        restricted=False,
        role=list(role),
    )


def test_basic_info_sheet_renders_5e_layout():
    session = Session(root_path=os.path.join(REPO_ROOT, 'tests', 'fixtures'))
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    html = _render_basic_info(fighter)

    assert 'class="dnd-sheet"' in html
    assert 'class="dnd-sheet-header"' in html
    assert 'class="dnd-sheet-body"' in html
    assert 'Strength' in html
    assert 'Dexterity' in html
    assert 'Saving Throws' in html
    assert 'Acrobatics' in html
    assert 'Passive Perception' in html
    assert 'id="max-hp-input"' in html
    assert 'id="current-hp-input"' in html
    assert 'id="temp-hp-input"' in html
    assert 'id="appearance-display-text"' in html
    assert 'id="rest-btn-short"' in html
    assert 'Features &amp; Traits' in html or 'Features & Traits' in html
    assert 'auto-die-roll' in html
    assert 'dnd-prof-pip' in html
    assert 'ft.' in html
    assert 'Other Proficiencies' in html
    assert 'Armor' in html
    assert 'Weapons' in html
    assert 'Light Armor' in html
    assert 'Simple' in html
    assert 'Defenses' in html
    assert 'Conditions' in html
    assert 'Inspiration' in html
    assert 'id="inspiration-pip"' in html
    assert 'Heroic Inspiration' not in html


def test_fighter_other_proficiencies_split_armor_and_weapons():
    session = Session(root_path=os.path.join(REPO_ROOT, 'tests', 'fixtures'))
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    other = fighter.other_proficiencies()
    assert 'light_armor' in other['armor']
    assert 'shields' in other['armor']
    assert 'simple' in other['weapons']
    assert 'martial' in other['weapons']
    assert 'longsword' in other['weapons']
    assert 'light_armor' not in other['weapons']


def test_sheet_defenses_conditions_and_inspiration():
    session = Session(root_path=os.path.join(REPO_ROOT, 'tests', 'fixtures'))
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    fighter.resistances.append('fire')
    fighter.damage_immunities.append('poison')
    fighter.condition_immunities.append('charmed')
    fighter.statuses.extend(['prone', 'poisoned', 'squeezed'])
    fighter.grant_inspiration()

    assert fighter.has_inspiration()
    assert fighter.inspiration_label() == 'Inspiration'
    assert 'Prone' in fighter.sheet_conditions()
    assert 'Poisoned' in fighter.sheet_conditions()
    assert 'Squeezed' not in fighter.sheet_conditions()
    defenses = fighter.sheet_defenses()
    assert 'fire' in defenses['resistances']
    assert 'poison' in defenses['immunities']
    assert 'charmed' in defenses['condition_immunities']

    html = _render_basic_info(fighter)
    assert 'Defenses' in html
    assert 'Fire' in html
    assert 'Poison' in html
    assert 'Charmed' in html
    assert 'Prone' in html
    assert 'Poisoned' in html
    assert 'Squeezed' not in html
    assert 'dnd-insp-pip filled' in html

    data = fighter.to_dict()
    restored = PlayerCharacter.from_dict(data)
    assert restored.has_inspiration()
    restored.consume_inspiration()
    assert not restored.has_inspiration()


def test_heroic_inspiration_label_on_2024_ruleset():
    from natural20.ruleset import get_ruleset

    session = Session(root_path=os.path.join(REPO_ROOT, 'tests', 'fixtures'))
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    session.ruleset = get_ruleset('5e-2024')
    assert fighter.inspiration_label() == 'Heroic Inspiration'
    html = _render_basic_info(fighter)
    assert 'Heroic Inspiration' in html
    assert 'id="inspiration-pip"' in html
