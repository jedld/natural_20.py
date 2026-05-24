"""Auth blueprint — login, logout, character selection routes.

Extracted from webapp/app.py.
Routes: /login, /logout, /character_selection, /select_character
"""
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template

from .helpers.runtime_state import (
    get_logins,
    get_current_game,
    get_controllers,
    get_index_data,
    get_title,
    get_login_background,
    get_character_selection_background,
    get_builder_only_mode,
    get_logger,
)
from .helpers.auth_utils import logged_in, user_role
from .helpers.pvp import (
    selectable_character_entry,
    pvp_team_config,
    pvp_team_counts,
    ensure_controller_entry,
    assign_character_team_and_spawn,
    ensure_character_entity_loaded,
)
from .helpers.template_globals import entities_controlled_by

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    logger = get_logger()
    if get_builder_only_mode():
        return redirect(url_for('character.character_builder'))
    if request.method == 'POST':
        username = request.form['username'].lower()
        password = request.form['password']

        logins = get_logins()
        login_info = next((login for login in logins if login["name"].lower() == username), None)
        if login_info and login_info["password"] == password:
            session['username'] = username

            if 'dm' in login_info.get('role', []):
                current_game = get_current_game()
                current_game.set_pov_entity_for_user(username, None)
                try:
                    current_game.switch_map_for_user(username, current_game.get_current_battle_map().name)
                except Exception:
                    logger.exception(f"Failed to switch DM {username} to the current battle map")

            # Spawn deferred PCs for this user on first login
            current_game = get_current_game()
            current_game.spawn_player_for_user(username)

            # Check if user has any assigned controllers
            user_entities = entities_controlled_by(username)
            if not user_entities and 'dm' not in user_role():
                # Redirect to character selection if no characters assigned
                return jsonify(status='character_selection_required')

            return jsonify(status='ok')
        return jsonify(error="Invalid Login Credentials")

    return render_template('login.html', title=get_title(), background=get_login_background())


@auth_bp.route('/character_selection', methods=['GET'], endpoint='character_selection')
def character_selection():
    if not logged_in():
        return redirect(url_for('auth.login'))

    # Check if user already has characters assigned
    user_entities = entities_controlled_by(session['username'])
    if user_entities:
        return redirect(url_for('navigation.index'))

    # Get list of selectable characters from index.json
    index_data = get_index_data()
    selectable_characters = index_data.get("selectable_characters", [])

    # Find characters that are already taken by other users
    taken_characters = set()
    controllers = get_controllers()
    for controller in controllers:
        if controller['controllers']:  # If anyone is assigned to this character
            taken_characters.add(controller['entity_uid'])

    return render_template('character_selection.html',
                         title=get_title(),
                         background=get_character_selection_background(),
                         selectable_characters=selectable_characters,
                         taken_characters=taken_characters,
                         pvp_team_config=pvp_team_config(),
                         pvp_team_counts=pvp_team_counts())


@auth_bp.route('/select_character', methods=['POST'], endpoint='select_character')
def select_character():
    logger = get_logger()
    if not logged_in():
        return jsonify(error="Not logged in"), 401

    character_name = request.form.get('character')
    selected_team = (request.form.get('team') or '').lower()
    username = session['username']

    if not character_name:
        return jsonify(error="No character specified")

    # Check if character exists in selectable characters
    character_exists = selectable_character_entry(character_name) is not None

    if not character_exists:
        return jsonify(error="Invalid character selection")

    # Check if character is already taken
    controllers = get_controllers()
    for controller in controllers:
        if controller['entity_uid'] == character_name and controller['controllers']:
            return jsonify(error="Character is already taken")

    team_config = pvp_team_config()
    if team_config and not selected_team:
        return jsonify(error='Choose Team A or Team B before confirming your slot')

    # Assign character to user
    controller_entry = ensure_controller_entry(character_name)
    if username not in controller_entry['controllers']:
        controller_entry['controllers'].append(username)

    if team_config:
        try:
            assign_character_team_and_spawn(character_name, selected_team)
        except ValueError as exc:
            if controller_entry and username in controller_entry.get('controllers', []):
                controller_entry['controllers'].remove(username)
            return jsonify(error=str(exc))
    else:
        # Non-PvP flow: materialize the selected character (loads the PC sheet
        # and reserves a player_spawn_point if needed) so the subsequent
        # spawn_player_for_user call has something deferred to place.
        try:
            if ensure_character_entity_loaded(character_name) is None:
                if controller_entry and username in controller_entry.get('controllers', []):
                    controller_entry['controllers'].remove(username)
                return jsonify(error='No spawn slot available for this character')
        except Exception as exc:
            logger.exception(f"Failed to materialize character {character_name}")
            if controller_entry and username in controller_entry.get('controllers', []):
                controller_entry['controllers'].remove(username)
            return jsonify(error=f'Failed to load character: {exc}')

    # Update the current_game controllers if needed
    current_game = get_current_game()
    current_game._setup_controllers()

    # Spawn deferred PC for this user after character selection
    current_game.spawn_player_for_user(username)

    # Proactively set POV and sync current map to the selected character to avoid stale map on first load
    try:
        entity = current_game.get_entity_by_uid(character_name)
        if entity is not None:
            current_game.set_pov_entity_for_user(username, entity)
            try:
                entity_map = current_game.get_map_for_entity(entity)
                if entity_map is not None:
                    current_game.switch_map_for_user(username, entity_map.name)
            except Exception:
                pass
    except Exception:
        # Non-fatal; index() will still attempt to correct on first render
        pass

    logger.info(f"User {username} selected character {character_name}")
    return jsonify(status='ok')


@auth_bp.route('/logout', methods=['POST', 'GET'], endpoint='logout')
def logout():
    session['username'] = None
    return redirect(url_for('auth.login'))
