"""Defensive Cast (2024) and the shared reaction-spell budget.

Covers the engine layer that both editions share:

* the per-turn reaction *spell* budget (``Battle.can_cast_reaction_spell``),
* the edition-dependent Shield AC bonus (+2014: +5, +2024: +2),
* the 2024 Defensive Cast reaction window (Bolster / Defensive Dueling),
  including its async (player) prompt path.
"""

import json
import random
import shutil
from pathlib import Path

import pytest
import yaml

from natural20.action import Action, AsyncReactionHandler
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.controller import Controller
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.ruleset.ruleset_2014 import Ruleset2014
from natural20.ruleset.ruleset_2024 import Ruleset2024
from natural20.session import Session
from natural20.spell.defensive_cast_spell import (
    DefensiveCastSpell, choose_defensive_cast_option,
)
from natural20.spell.shield_spell import ShieldSpell
from natural20.utils.attack_util import after_attack_roll_hook

FIXTURES = Path(__file__).resolve().parent / "fixtures"

from tests.ranger_spell_helpers import missing_packs

PACK_SKIP = pytest.mark.skipif(
    missing_packs(['players_handbook_2024']),
    reason='players_handbook_2024 expansion pack not installed')


class _ReactionController(Controller):
    """Records reaction prompts; accepts options like the AI controllers do."""

    def __init__(self, session, accept=True):
        self.state = {}
        self.session = session
        self.battle_data = {}
        self.user = None
        self.accept = accept
        self.prompts = []

    def select_reaction(self, entity, battle, map, valid_actions, event):
        self.prompts.append((event, list(valid_actions)))
        if not self.accept or not valid_actions:
            return None
        if (event or {}).get('type') == 'defensive_cast':
            return choose_defensive_cast_option(entity, battle, valid_actions, event)
        return valid_actions[0]

    def select_action(self, battle, entity, available_actions):
        # Legacy synchronous reaction path (no original_action threaded).
        return available_actions[0] if self.accept and available_actions else None


class _AsyncController(_ReactionController):
    """Mimics WebController: hands back a generator for a human to answer."""

    def select_reaction(self, entity, battle, map, valid_actions, event):
        self.prompts.append((event, list(valid_actions)))
        yield battle, entity, valid_actions


class _Roll:
    """Static attack-roll stand-in for the reaction windows."""

    def __init__(self, total, nat=None):
        self.total = total
        self.nat = total if nat is None else nat

    def result(self):
        return self.total

    def nat_20(self):
        return self.nat == 20

    def nat_1(self):
        return self.nat == 1


def _2014_session():
    random.seed(4242)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    return session


def _2024_session(tmp_path):
    random.seed(4242)
    dest = tmp_path / "campaign"
    shutil.copytree(FIXTURES, dest, ignore=shutil.ignore_patterns("tmp", "__pycache__", "*.pyc"))
    with (dest / "game.yml").open("r", encoding="utf-8") as fh:
        game = yaml.safe_load(fh) or {}
    game["ruleset"] = "5e-2024"
    with (dest / "game.yml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(game, fh)
    (dest / "index.json").write_text(json.dumps(
        {"expansion_packs": {"players_handbook_2024": "players_handbook_2024"}}))
    return Session(root_path=str(dest), event_manager=EventManager())


def _battle(session, character_file=None):
    battle_map = Map(session, 'large_map')
    battle = Battle(session, battle_map)
    wizard = PlayerCharacter.load(session, character_file or 'counterspell_wizard.yml')
    mage = session.npc('test_counter_mage', {'name': 'Hostile Mage'})
    battle.add(wizard, 'a', position=[2, 6])
    battle.add(mage, 'b', position=[6, 6])
    battle.start(combat_order=[mage, wizard])
    wizard.reset_turn(battle)
    mage.reset_turn(battle)
    battle.set_current_turn(mage)
    return battle, battle_map, wizard, mage


# --- reaction-spell budget ----------------------------------------------------

def test_budget_defaults_and_reset():
    session = _2014_session()
    battle, _map, wizard, _mage = _battle(session)
    assert battle.can_cast_reaction_spell(wizard)
    battle.consume_reaction_spell(wizard)
    assert not battle.can_cast_reaction_spell(wizard)
    wizard.reset_turn(battle)
    assert battle.can_cast_reaction_spell(wizard)


def test_consume_resource_accepts_reaction_spell():
    session = _2014_session()
    battle, _map, wizard, _mage = _battle(session)
    battle.consume(wizard, 'reaction_spell')
    assert battle.entity_state_for(wizard)['reaction_spell'] == 0


def test_spent_budget_blocks_reaction_spells_but_not_opportunity_attacks():
    session = _2014_session()
    battle, _map, wizard, mage = _battle(session)
    # The creature still has its reaction...
    assert wizard.has_reaction(battle)
    # ...but if the reaction-spell budget is spent, no reaction *spell*
    # (Shield, Counterspell, ...) may be cast.
    battle.consume_reaction_spell(wizard)
    assert SpellAction.can_cast(wizard, battle, 'counterspell') is False
    assert SpellAction.can_cast(wizard, battle, 'shield') is False
    assert wizard.has_reaction(battle)


def test_casting_a_reaction_spell_spends_the_budget():
    session = _2014_session()
    battle, _map, wizard, mage = _battle(session)
    controller = _ReactionController(session)
    battle.set_controller_for(wizard, controller)
    # Hostile Mage casts; the wizard counterspells (2014 auto-success at 3rd
    # slot vs 1st-level spell).
    hostile = SpellAction.build(session, mage)['next'](['magic_missile', 0])['next']([wizard])
    hostile.resolve(session, _map, {'battle': battle})
    assert 'spell_countered' in [item['type'] for item in hostile.result]
    battle.commit(hostile)
    assert not battle.can_cast_reaction_spell(wizard)
    # A second reaction spell the same turn is refused...
    hostile2 = SpellAction.build(session, mage)['next'](['magic_missile', 0])['next']([wizard])
    hostile2.resolve(session, _map, {'battle': battle})
    assert 'spell_countered' not in [item['type'] for item in hostile2.result]
    # ...until the wizard's next turn resets both budgets.
    wizard.reset_turn(battle)
    assert battle.can_cast_reaction_spell(wizard)


# --- edition-dependent Shield bonus -------------------------------------------

def test_shield_ac_bonus_is_edition_scoped():
    assert Ruleset2014().shield_ac_bonus() == 5
    assert Ruleset2024().shield_ac_bonus() == 2


def test_shield_effect_uses_session_ruleset():
    class _Holder:
        pass

    session2014 = _2014_session()
    holder = _Holder()
    holder.session = session2014
    assert ShieldSpell.ac_bonus(holder, {'value': 0}) == 5


@pytest.mark.parametrize('ruleset,expected', [(Ruleset2014(), 5), (Ruleset2024(), 2)])
def test_shield_window_near_miss_width_tracks_ruleset(ruleset, expected):
    session = _2014_session()
    battle, _map, wizard, mage = _battle(session)
    session.ruleset = ruleset
    controller = _ReactionController(session)
    battle.set_controller_for(wizard, controller)
    # Roll 17 vs AC 13: inside the 2014 +5 near-miss window (Shield would
    # save the attack) but outside the 2024 +2 window.
    force_miss, _events = after_attack_roll_hook(battle, wizard, mage, _Roll(17), 13, {})
    assert force_miss == (expected == 5)


# --- defensive cast (2024) ------------------------------------------------------

@pytest.fixture
def dc_setup(tmp_path):
    session = _2024_session(tmp_path)
    battle, battle_map, wizard, mage = _battle(session, 'defensive_cast_wizard.yml')
    controller = _ReactionController(session)
    battle.set_controller_for(wizard, controller)
    return session, battle, battle_map, wizard, mage, controller


def _commit_events(session, battle, source, events):
    action = Action(session, source, 'test')
    action.result = list(events)
    battle.commit(action)
    return action


@PACK_SKIP
def test_defensive_cast_offered_on_a_hit(dc_setup):
    session, battle, _map, wizard, mage, controller = dc_setup
    force_miss, events = after_attack_roll_hook(
        battle, wizard, mage, _Roll(15), 14, {})
    types = [item['type'] for item in events]
    assert 'defensive_cast' in types
    event = next(item for item in events if item['type'] == 'defensive_cast')
    assert event['cast_option']['id'] == 'dueling'
    # 15 < 14 + 2: Defensive Dueling turns the hit into a miss.
    assert force_miss is True
    assert not battle.can_cast_reaction_spell(wizard)
    assert not wizard.has_reaction(battle)


@PACK_SKIP
def test_defensive_cast_not_offered_on_a_miss(dc_setup):
    session, battle, _map, wizard, mage, controller = dc_setup
    _force_miss, events = after_attack_roll_hook(
        battle, wizard, mage, _Roll(10), 14, {})
    assert not [e for e in events if e['type'] == 'defensive_cast']
    assert controller.prompts == []


@PACK_SKIP
def test_bolster_grants_temp_hp_on_commit(dc_setup):
    session, battle, _map, wizard, mage, controller = dc_setup
    # Roll far above the Dueling window: only Bolster applies.
    controller.accept = False
    _force_miss, events = after_attack_roll_hook(
        battle, wizard, mage, _Roll(30), 14, {})
    assert events == [] and controller.prompts  # declined

    controller.accept = True
    _force_miss, events = after_attack_roll_hook(
        battle, wizard, mage, _Roll(30), 14, {})
    event = next(item for item in events if item['type'] == 'defensive_cast')
    assert event['cast_option']['id'] == 'bolster'
    _commit_events(session, battle, wizard, events)
    assert battle.entity_state_for(wizard)['temp_hp'] == 2


@PACK_SKIP
def test_dueling_registers_ac_effect_until_next_turn(dc_setup):
    session, battle, _map, wizard, mage, controller = dc_setup
    _force_miss, events = after_attack_roll_hook(
        battle, wizard, mage, _Roll(15), 14, {})
    _commit_events(session, battle, wizard, events)
    assert wizard.has_effect('ac_bonus')
    holder = _OptsHolder(entity=wizard)
    assert DefensiveCastSpell.ac_bonus(
        wizard, {'value': 0, 'effect': holder.effect(wizard)}) == 2
    # Expires at the start of the defender's next turn.
    wizard.reset_turn(battle)
    assert not wizard.has_effect('ac_bonus')


class _OptsHolder:
    def __init__(self, entity):
        self.entity = entity

    def effect(self, entity):
        for entry in entity.effects.get('ac_bonus', []):
            if entry.get('handler') is DefensiveCastSpell:
                return entry['effect']
        return None


@PACK_SKIP
def test_defensive_cast_declined_keeps_resources(dc_setup):
    session, battle, _map, wizard, mage, controller = dc_setup
    controller.accept = False
    force_miss, events = after_attack_roll_hook(
        battle, wizard, mage, _Roll(15), 14, {})
    assert events == []
    assert force_miss is False
    assert battle.can_cast_reaction_spell(wizard)
    assert wizard.has_reaction(battle)


@PACK_SKIP
def test_defensive_cast_async_prompt(dc_setup):
    session, battle, _map, wizard, mage, _controller = dc_setup
    controller = _AsyncController(session)
    battle.set_controller_for(wizard, controller)
    action = Action(session, mage, 'test')
    with pytest.raises(AsyncReactionHandler) as ctx:
        after_attack_roll_hook(battle, wizard, mage, _Roll(15), 14,
                               {'original_action': action})
    handler = ctx.value
    assert handler.reaction_type == 'defensive_cast'
    for _, _, valid_actions in handler.resolve():
        handler.send(valid_actions[0])

    # The attack action re-enters the window after the answer arrives.
    _force_miss, events = after_attack_roll_hook(
        battle, wizard, mage, _Roll(15), 14, {'original_action': action})
    events = [e for e in events if isinstance(e, dict)]
    assert any(e.get('type') == 'defensive_cast' for e in events)
    _commit_events(session, battle, mage, events)
    assert not battle.can_cast_reaction_spell(wizard)


@PACK_SKIP
def test_generic_controller_prefers_dueling(dc_setup):
    session, battle, _map, wizard, mage, _controller = dc_setup
    battle.set_controller_for(wizard, GenericController(session))
    force_miss, events = after_attack_roll_hook(
        battle, wizard, mage, _Roll(15), 14, {})
    events = [e for e in events if isinstance(e, dict)]
    dueling = [e for e in events if e.get('type') == 'defensive_cast'
               and e.get('cast_option', {}).get('id') == 'dueling']
    assert dueling and force_miss is True


@PACK_SKIP
def test_spell_not_prepared_no_prompt():
    # 2014 fixture wizard (no defensive_cast) must never be prompted, even
    # when running the same hook.
    session = _2014_session()
    battle, _map, wizard, mage = _battle(session, 'counterspell_wizard.yml')
    controller = _ReactionController(session)
    battle.set_controller_for(wizard, controller)
    after_attack_roll_hook(battle, wizard, mage, _Roll(15), 14, {})
    assert [p for p, _ in controller.prompts
           if p['type'] == 'defensive_cast'] == []


@PACK_SKIP
def test_choose_defensive_cast_option_prefers_ac():
    class _A:
        def __init__(self, option):
            self.opts = {'cast_option': option}

    bolster = _A({'id': 'bolster', 'temp_hp_base': 2})
    dueling = _A({'id': 'dueling', 'ac_bonus': 2})
    assert choose_defensive_cast_option(None, None, [bolster, dueling]) is dueling
    assert choose_defensive_cast_option(None, None, [bolster]) is bolster
    assert choose_defensive_cast_option(None, None, []) is None
