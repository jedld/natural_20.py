"""Character builder utility functions extracted from app.py.

These functions support character creation, editing, and import workflows
including YAML resolution, image handling, ability score computation, and
campaign registration.

Design:
    All functions use ``runtime_state`` accessors for global state to avoid
    circular imports. No Flask app context is required at import time.
"""

import json
import os
import re
import base64
import io
import logging

from PIL import Image, ImageDraw
import yaml

from .runtime_state import (
    get_current_game,
    get_game_session,
    get_index_data,
    get_builder_only_mode,
    get_controllers,
)

logger = logging.getLogger(__name__)

PREBUILT_CHARACTER_DIR = os.path.join('static', 'assets', 'prebuild_character')


# --------------------------------------------------------------------------- #
# Form parsing helpers
# --------------------------------------------------------------------------- #

def _parse_json_list_form(form, key):
    """Parse a JSON-encoded list from a Flask form field."""
    val = form.get(key)
    if not val:
        return []
    try:
        parsed = json.loads(val)
        if isinstance(parsed, list):
            return parsed
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_json_dict_form(form, key):
    """Parse a JSON-encoded dict from a Flask form field."""
    val = form.get(key)
    if not val:
        return {}
    try:
        parsed = json.loads(val)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}


# --------------------------------------------------------------------------- #
# Ability score helpers
# --------------------------------------------------------------------------- #

def _ability_mod(score):
    """Return the ability modifier for a given ability score."""
    try:
        score = int(score)
        return (score - 10) // 2
    except (ValueError, TypeError):
        return 0


# --------------------------------------------------------------------------- #
# Spell choice helpers
# --------------------------------------------------------------------------- #

def _spell_choice_caps(klass, level, ability, class_def):
    """Return the number of spells a class can prepare/learn at a given level.

    Returns
    -------
    dict
        Keys: 'cantrip_cap', 'level1_cap', 'spellbook_cap'.
    """
    klass_lower = str(klass or '').lower()
    lvl = max(1, int(level or 1))
    caps = {'cantrip_cap': 0, 'level1_cap': 0, 'spellbook_cap': 0}

    try:
        from natural20.entity_class.wizard import WIZARD_SPELL_SLOT_TABLE
        from natural20.entity_class.cleric import CLERIC_SPELL_SLOT_TABLE
        from natural20.entity_class.druid import DRUID_SPELL_SLOT_TABLE
        from natural20.entity_class.bard import BARD_SPELL_SLOT_TABLE
        from natural20.entity_class.warlock import WARLOCK_SPELL_SLOT_TABLE
        from natural20.entity_class.sorcerer import SORCERER_SPELL_SLOT_TABLE
        from natural20.entity_class.paladin import PALADIN_SPELL_SLOT_TABLE
        from natural20.entity_class.ranger import RANGER_SPELL_SLOT_TABLE
    except Exception:
        WIZARD_SPELL_SLOT_TABLE = []
        CLERIC_SPELL_SLOT_TABLE = []
        DRUID_SPELL_SLOT_TABLE = []
        BARD_SPELL_SLOT_TABLE = []
        WARLOCK_SPELL_SLOT_TABLE = []
        SORCERER_SPELL_SLOT_TABLE = []
        PALADIN_SPELL_SLOT_TABLE = []
        RANGER_SPELL_SLOT_TABLE = []

    slot_tables = {
        'wizard': WIZARD_SPELL_SLOT_TABLE,
        'cleric': CLERIC_SPELL_SLOT_TABLE,
        'druid': DRUID_SPELL_SLOT_TABLE,
        'bard': BARD_SPELL_SLOT_TABLE,
        'warlock': WARLOCK_SPELL_SLOT_TABLE,
        'sorcerer': SORCERER_SPELL_SLOT_TABLE,
        'paladin': PALADIN_SPELL_SLOT_TABLE,
        'ranger': RANGER_SPELL_SLOT_TABLE,
    }

    table = slot_tables.get(klass_lower) or []
    row = []
    if table and lvl <= len(table):
        row = table[lvl - 1]

    if row:
        if len(row) > 0:
            caps['cantrip_cap'] = max(0, int(row[0] or 0))
        if len(row) > 1:
            caps['level1_cap'] = max(0, int(row[1] or 0))

    # Known/prepared rules for early levels where engine supports custom builds.
    if klass_lower == 'wizard':
        caps['spellbook_cap'] = 6 + (max(1, lvl) - 1) * 2
        caps['level1_cap'] = max(caps['level1_cap'], max(1, lvl + _ability_mod((ability or {}).get('int', 10))))
    elif klass_lower in ('cleric', 'druid', 'paladin'):
        spell_ability = str((class_def or {}).get('spellcasting_ability') or ('wisdom' if klass_lower in ('cleric', 'druid') else 'charisma'))
        key = spell_ability[:3].lower()
        caps['level1_cap'] = max(caps['level1_cap'], max(1, lvl + _ability_mod((ability or {}).get(key, 10))))
    elif klass_lower == 'bard':
        bard_known = [0, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14,
                      15, 15, 16, 18, 19, 19, 20, 22, 22, 22]
        caps['level1_cap'] = max(caps['level1_cap'], bard_known[min(lvl, len(bard_known) - 1)])
    elif klass_lower == 'warlock':
        warlock_known = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10,
                         11, 11, 12, 12, 13, 13, 14, 14, 15, 15]
        caps['level1_cap'] = max(caps['level1_cap'], warlock_known[min(lvl, len(warlock_known) - 1)])
    elif klass_lower == 'sorcerer':
        sorc_known = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
                      12, 12, 13, 13, 14, 14, 15, 15, 15, 15]
        caps['level1_cap'] = max(caps['level1_cap'], sorc_known[min(lvl, len(sorc_known) - 1)])
    elif klass_lower == 'ranger':
        ranger_known = [0, 0, 2, 3, 3, 4, 4, 5, 5, 6, 6,
                        7, 7, 8, 8, 9, 9, 10, 10, 11, 11]
        caps['level1_cap'] = max(caps['level1_cap'], ranger_known[min(lvl, len(ranger_known) - 1)])

    return caps


# --------------------------------------------------------------------------- #
# Class and feat choices application
# --------------------------------------------------------------------------- #

def _apply_class_and_feat_choices(pc, klass, level, classes_def, selected_skills,
                                  selected_cantrips, selected_level1, selected_feats):
    """Apply class and feat choices to a player character dict.

    This function validates selections against the class definition, applies
    spell choice caps, and handles wizard spellbook construction.

    Parameters
    ----------
    pc : dict
        The player character dictionary to mutate.
    klass : str
        The class name (e.g. 'Wizard').
    level : int
        The character level.
    classes_def : dict
        The full class definitions mapping.
    selected_skills : list[str]
        Skill names chosen by the user.
    selected_cantrips : list[str]
        Cantrip names chosen by the user.
    selected_level1 : list[str]
        Level-1 spell names chosen by the user.
    selected_feats : list[str]
        Feat names chosen by the user.
    """
    cdef = (classes_def or {}).get(klass, {}) or {}

    # Skills
    max_skills = int(cdef.get('available_skills_choices', 0) or 0)
    available_skills = cdef.get('available_skills', []) or []
    if max_skills and available_skills:
        valid_skills = [s for s in selected_skills if s in available_skills][:max_skills]
        if valid_skills:
            pc['skills'] = valid_skills

    # Spells
    spell_list = cdef.get('spell_list', {}) or {}
    can_list = spell_list.get('cantrip', []) or []
    lvl1_list = spell_list.get('level_1', []) or []
    caps = _spell_choice_caps(klass, level, pc.get('ability') or {}, cdef)

    cantrip_cap = min(caps['cantrip_cap'], len(can_list)) if can_list else 0
    level1_cap = min(caps['level1_cap'], len(lvl1_list)) if lvl1_list else 0

    prepared = []
    if cantrip_cap > 0:
        prepared.extend([s for s in selected_cantrips if s in can_list][:cantrip_cap])
    if level1_cap > 0:
        prepared.extend([s for s in selected_level1 if s in lvl1_list][:level1_cap])

    if prepared:
        pc['prepared_spells'] = list(dict.fromkeys(prepared))
    elif 'prepared_spells' in pc:
        pc.pop('prepared_spells', None)

    if str(klass).lower() == 'wizard':
        spellbook_cap = max(0, int(caps.get('spellbook_cap') or 0))
        if spellbook_cap > 0:
            book = [s for s in lvl1_list if s in (pc.get('prepared_spells') or [])]
            for spell in lvl1_list:
                if len(book) >= spellbook_cap:
                    break
                if spell not in book:
                    book.append(spell)
            pc['spellbook'] = book[:spellbook_cap]

    # Feats
    feat_options = cdef.get('feat_choices') or cdef.get('available_feats') or []
    feat_count = int(cdef.get('feat_choices_count') or cdef.get('available_feats_choices') or 0)
    if feat_options:
        feats = [f for f in selected_feats if f in feat_options]
        if feat_count > 0:
            feats = feats[:feat_count]
        pc['feats'] = list(dict.fromkeys(feats))
    elif selected_feats:
        pc['feats'] = list(dict.fromkeys(selected_feats))


# --------------------------------------------------------------------------- #
# Character YAML path resolution
# --------------------------------------------------------------------------- #

def _resolve_character_yaml_path(character_name):
    game_session = get_game_session()
    chars_dir = os.path.join(game_session.root_path, 'characters')
    if not os.path.isdir(chars_dir):
        return None

    direct_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(character_name or ''))
    if direct_name:
        direct_path = os.path.join(chars_dir, f"{direct_name}.yml")
        if os.path.exists(direct_path):
            return direct_path

    target = str(character_name or '').lower()
    for file_name in os.listdir(chars_dir):
        if not file_name.endswith('.yml'):
            continue
        file_path = os.path.join(chars_dir, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            continue

        candidate_uid = str(data.get('entity_uid') or '').lower()
        candidate_name = str(data.get('name') or '').lower()
        if candidate_uid == target or candidate_name == target:
            return file_path

    return None


def _can_edit_character(character_name):
    from flask import session as flask_session
    from .pvp import selectable_character_entry
    from .template_globals import controller_of as _controller_of
    from .auth_utils import roles_for_username

    if get_builder_only_mode():
        return True
    if 'dm' in roles_for_username(flask_session.get('username')):
        return True
    username = flask_session.get('username')
    if not username:
        return False
    if _controller_of(character_name, username):
        return True

    # Selection-flow editing: allow a logged-in player to edit a selectable
    # character before confirming ownership, as long as another user has not
    # already claimed it.
    entry = selectable_character_entry(character_name)
    if entry is not None:
        for controller in get_controllers():
            if controller.get('entity_uid') != character_name:
                continue
            controllers = controller.get('controllers') or []
            if controllers and username not in controllers:
                return False
        return True

    return False


# --------------------------------------------------------------------------- #
# Image processing helpers
# --------------------------------------------------------------------------- #

def _make_circular_token(pil_img, size=256, ring_width=4, ring_color=(74, 47, 25, 255)):
    """Crop and mask a PIL image into a circular token with an optional ring.

    Parameters
    ----------
    pil_img : Image.Image
        The source image.
    size : int
        Output canvas size in pixels (square).
    ring_width : int
        Width of the outer ring border.
    ring_color : tuple[int]
        RGBA color for the ring.

    Returns
    -------
    Image.Image
        An RGBA image of the circular token.
    """
    # Convert to RGBA if necessary
    if pil_img.mode != 'RGBA':
        pil_img = pil_img.convert('RGBA')

    # Crop to center square
    width, height = pil_img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    pil_img = pil_img.crop((left, top, left + side, top + side))

    # Resize to target size
    pil_img = pil_img.resize((size, size), Image.LANCZOS)

    # Create circular mask
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)

    # Apply mask
    result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    result.paste(pil_img, (0, 0), mask)

    # Draw ring border (matches original app.py implementation)
    if ring_width and ring_width > 0:
        draw = ImageDraw.Draw(result)
        for i in range(ring_width):
            draw.ellipse(
                (i, i, size - 1 - i, size - 1 - i),
                outline=ring_color,
            )

    return result


def _decode_data_url_image(data_url):
    """Decode a ``data:image/...;base64,...`` URL into a PIL Image, or None.

    Parameters
    ----------
    data_url : str
        A data URL containing base64-encoded image bytes.

    Returns
    -------
    Image.Image or None
    """
    try:
        if not isinstance(data_url, str):
            return None
        match = re.match(r'data:image/[^;]+;base64,(.+)', data_url)
        if not match:
            return None
        img_data = base64.b64decode(match.group(1))
        return Image.open(io.BytesIO(img_data))
    except Exception:
        return None


def _resolve_prebuilt_character_image(name):
    """Find a prebuilt character image file by name.

    Searches the campaign's ``assets/characters/`` folder, then falls back
    to the global templates directory.

    Parameters
    ----------
    name : str
        The character name (without extension).

    Returns
    -------
    str or None
        The resolved filesystem path, or ``None``.
    """
    game_session = get_game_session()

    # Try campaign directory
    for ext in ['.png', '.webp', '.jpg', '.jpeg']:
        path = os.path.join(game_session.root_path, 'assets', 'characters', f'{name}{ext}')
        if os.path.exists(path):
            return path

    # Fall back to templates
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        'templates', 'assets', 'characters',
    )
    for ext in ['.png', '.webp', '.jpg', '.jpeg']:
        path = os.path.join(templates_dir, f'{name}{ext}')
        if os.path.exists(path):
            return path

    return None


def _save_character_images(entity_uid, assets_dir, profile_pil=None, token_pil=None):
    """Save profile and token images for a character to disk.

    Parameters
    ----------
    entity_uid : str
        The character UID (used as the filename stem).
    assets_dir : str
        Parent directory for character assets.
    profile_pil : Image.Image or None
        The profile portrait image (saved as ``profile.png``).
    token_pil : Image.Image or None
        The token image (saved as ``token.png``).
    """
    char_dir = os.path.join(assets_dir, 'characters')
    os.makedirs(char_dir, exist_ok=True)

    if profile_pil is not None:
        profile_path = os.path.join(char_dir, f'{entity_uid}_profile.png')
        profile_pil.save(profile_path)

    if token_pil is not None:
        token_path = os.path.join(char_dir, f'{entity_uid}_token.png')
        token_pil.save(token_path)


def _load_character_image_from_request(req, file_field, prebuilt_field, data_url_field=None):
    """Extract a character image from an upload request.

    Tries the following sources in order:
    1. Uploaded file (``file_field``)
    2. Prebuilt image reference (``prebuilt_field``)
    3. Data URL (``data_url_field``)

    Parameters
    ----------
    req : flask.Request
        The incoming Flask request.
    file_field : str
        Form field name for the file upload.
    prebuilt_field : str
        Form field name for a prebuilt image reference.
    data_url_field : str or None
        Optional form field name for a data URL.

    Returns
    -------
    Image.Image or None
    """
    # Try file upload first
    if file_field in req.files:
        file_item = req.files[file_field]
        if file_item and file_item.filename:
            try:
                return Image.open(file_item.stream)
            except Exception:
                pass

    # Try prebuilt image reference
    prebuilt_name = req.form.get(prebuilt_field)
    if prebuilt_name:
        path = _resolve_prebuilt_character_image(prebuilt_name)
        if path:
            try:
                return Image.open(path)
            except Exception:
                pass

    # Try data URL
    if data_url_field:
        data_url = req.form.get(data_url_field)
        if data_url:
            img = _decode_data_url_image(data_url)
            if img is not None:
                return img

    return None


# --------------------------------------------------------------------------- #
# Campaign registration
# --------------------------------------------------------------------------- #

def _register_new_character_in_campaign(pc, safe_name):
    """Place a new PC on the default map and expose it on the selection screen.

    Parameters
    ----------
    pc : dict
        The player character dictionary.
    safe_name : str
        The sanitized character name.
    """
    from natural20.player_character import PlayerCharacter

    current_game = get_current_game()
    game_session = get_game_session()
    index_data = get_index_data()

    entity_uid = pc.get('entity_uid') or safe_name.lower()

    if get_builder_only_mode():
        return

    try:
        pc_entity = PlayerCharacter.load(game_session, f'characters/{safe_name}.yml')
        target_map = game_session.maps.get('index') or next(iter(game_session.maps.values()))
        width, height = target_map.size
        pos = None
        for y in range(height):
            for x in range(width):
                if not target_map.entity_at(x, y):
                    pos = (x, y)
                    break
            if pos:
                break
        if not pos:
            pos = (0, 0)
        target_map.add(pc_entity, pos[0], pos[1], group='a')
    except Exception:
        logger.exception('Failed to place new character on map')

    try:
        index_json_path = os.path.join(game_session.root_path, 'index.json')
        if os.path.exists(index_json_path):
            with open(index_json_path, 'r') as jf:
                idx = json.load(jf)
        else:
            idx = {}
        selectable = idx.get('selectable_characters') or []
        lower = str(entity_uid).lower()
        if not any(c.get('name', '').lower() == lower for c in selectable):
            selectable.append({
                'name': lower,
                'file': f'characters/{lower}.png',
                'description': pc.get('description', lower),
            })
        idx['selectable_characters'] = selectable
        with open(index_json_path, 'w') as jf:
            json.dump(idx, jf, indent=2)
        try:
            index_data['selectable_characters'] = selectable
        except Exception:
            logger.exception('Failed to update in-memory selectable_characters')
    except Exception:
        logger.exception('Failed to update index.json with new character')
