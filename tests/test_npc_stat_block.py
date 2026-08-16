"""NPC 5e creature stat-block payload, access, and template smoke tests."""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from natural20.session import Session
from webapp.blueprints.helpers.npc_stat_block import (
    build_npc_stat_block,
    can_view_npc_stat_block,
    format_challenge_rating,
    format_npc_action,
    format_size_type_alignment,
    format_speed_line,
    is_player_controlled_npc,
)
from webapp.blueprints.helpers.template_globals import ability_mod_str, format_languages


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATE_DIR = os.path.join(REPO_ROOT, 'n20-webapp', 'webapp', 'templates')


def _session():
    return Session(root_path=os.path.join(REPO_ROOT, 'tests', 'fixtures'))


def _render_npc_block(entity, role=('dm',), restricted=False):
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(['html']),
    )
    env.filters['mod_str'] = ability_mod_str
    env.globals.update({
        'format_languages': format_languages,
        'can_rest_for': lambda _uid: False,
        'character_description_suppressed_for': lambda entity, viewer_is_dm=False: False,
        't': lambda key: key,
    })
    return env.get_template('_npc_stat_block.html').render(
        entity=entity,
        npc_block=build_npc_stat_block(entity),
        battle=None,
        restricted=restricted,
        role=list(role),
    )


def _render_public_card(entity, role=('player',), suppress=False):
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(['html']),
    )
    env.globals.update({
        'character_description_suppressed_for': lambda _entity, viewer_is_dm=False: suppress and not viewer_is_dm,
    })
    return env.get_template('_npc_public_card.html').render(
        entity=entity,
        restricted=True,
        role=list(role),
    )


def test_format_challenge_rating_fractions():
    assert format_challenge_rating(0.25) == '1/4'
    assert format_challenge_rating(0.5) == '1/2'
    assert format_challenge_rating(2) == '2'
    assert format_challenge_rating(0) == '0'


def test_goblin_stat_block_payload():
    goblin = _session().npc('goblin')
    block = build_npc_stat_block(goblin)

    assert block['name']
    assert 'Small humanoid' in block['size_type_alignment']
    assert 'goblinoid' in block['size_type_alignment']
    assert 'neutral evil' in block['size_type_alignment']
    assert block['ac'] == 15
    assert block['speed'] == '30 ft.'
    assert 'Stealth +6' in block['skills']
    assert 'darkvision 60 ft.' in block['senses']
    assert '1/4' in block['challenge']
    assert '50 XP' in block['challenge']
    assert any(trait['name'] == 'Nimble Escape' for trait in block['traits'])
    action_names = [action['name'] for action in block['actions']]
    assert 'Scimitar' in action_names
    scimitar = next(action for action in block['actions'] if action['name'] == 'Scimitar')
    assert 'Melee Weapon Attack' in scimitar['text']
    assert '+4 to hit' in scimitar['text']
    assert 'slashing' in scimitar['text']


def test_specter_defenses_and_fly_speed():
    specter = _session().npc('specter')
    block = build_npc_stat_block(specter)
    assert 'fly 50 ft.' in block['speed']
    assert 'Necrotic' in block['immunities']
    assert 'Poison' in block['immunities']
    assert any(trait['name'] == 'Incorporeal Movement' for trait in block['traits'])


def test_melee_action_includes_on_hit_text():
    wolf = _session().npc('wolf')
    bite = next(action for action in wolf.properties['actions'] if action['name'] == 'Bite')
    formatted = format_npc_action(bite)
    assert formatted['name'] == 'Bite'
    assert 'Melee Weapon Attack' in formatted['text']
    assert 'knocked prone' in formatted['text']


def test_size_type_alignment_and_speed_helpers():
    goblin = _session().npc('goblin')
    line = format_size_type_alignment(goblin)
    assert line.startswith('Small humanoid')
    assert format_speed_line(goblin) == '30 ft.'


def test_player_access_to_npc_stat_block():
    goblin = _session().npc('goblin')
    assert can_view_npc_stat_block(goblin, role=['dm']) is True
    assert can_view_npc_stat_block(goblin, role=['player'], owners=[]) is False
    assert is_player_controlled_npc(goblin, owners=['gomerin']) is True
    assert can_view_npc_stat_block(goblin, role=['player'], owners=['gomerin']) is True


def test_npc_stat_block_template_looks_like_5e():
    goblin = _session().npc('goblin')
    html = _render_npc_block(goblin)
    assert 'class="stat-block"' in html
    assert 'Armor Class' in html
    assert 'Hit Points' in html
    assert 'Challenge' in html
    assert 'Nimble Escape' in html
    assert 'Scimitar' in html
    assert 'class="dnd-sheet"' not in html
    assert 'Class &amp; Level' not in html
    assert 'id="current-hp-input"' in html


def test_npc_public_card_hides_combat_stats():
    goblin = _session().npc('goblin')
    html = _render_public_card(goblin)
    assert 'class="npc-public-card"' in html
    assert goblin.label() in html
    assert 'Armor Class' not in html
    assert 'Challenge' not in html
    assert 'Nimble Escape' not in html
    assert goblin.description() in html


def test_npc_public_card_can_suppress_description():
    goblin = _session().npc('goblin')
    html = _render_public_card(goblin, suppress=True)
    assert goblin.label() in html
    assert goblin.description() not in html


def test_spellcaster_stat_block_includes_save_dc():
    wizard = _session().npc('test_wizard')
    block = build_npc_stat_block(wizard)
    casting = block['spellcasting']
    assert casting is not None
    assert casting['ability'] == 'Intelligence'
    assert casting['save_dc'] == 13
    assert casting['attack_bonus'] == 5
    assert casting['attack_bonus_signed'] == '+5'
    html = _render_npc_block(wizard)
    assert 'spell save DC 13' in html
    assert '+5 to hit with spell attacks' in html
    assert 'Intelligence' in html


def test_acolyte_stat_block_matches_mm_spellcasting_dc():
    acolyte = _session().npc('acolyte')
    block = build_npc_stat_block(acolyte)
    casting = block['spellcasting']
    assert casting['ability'] == 'Wisdom'
    assert casting['save_dc'] == 12
    assert casting['attack_bonus_signed'] == '+4'
    html = _render_npc_block(acolyte)
    assert 'spell save DC 12' in html
    assert '+4 to hit with spell attacks' in html
    assert 'Cure Wounds' in html


def test_spell_save_dc_yaml_override():
    wizard = _session().npc('test_wizard', {'overrides': {'spell_save_dc': 17}})
    casting = build_npc_stat_block(wizard)['spellcasting']
    assert casting['save_dc'] == 17
    assert casting['attack_bonus'] == 5
