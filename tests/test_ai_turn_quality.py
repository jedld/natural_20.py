"""Regressions from combat-log reviews: wasted turns, pointless options and
movement, concentration bookkeeping, and callout menus."""
import random
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from natural20.actions.attack_action import AttackAction
from natural20.actions.hide_action import HideBonusAction
from natural20.actions.interact_action import InteractAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.polymorph_spell import PolymorphSpell
from natural20.utils import pointless_actions, polymorph
from natural20.utils.combat_strategy import strategy_options
from natural20.utils.jev_decision import JevActionPlanner, _oa_risk


@pytest.fixture
def world():
    random.seed(7000)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'battle_sim')
    battle = Battle(session, battle_map)
    return session, battle_map, battle


def _start(battle, *entities):
    battle.start()
    for e in entities:
        e.reset_turn(battle)
    battle.set_current_turn(entities[0])


def _planner(session, battle, battle_map, entity):
    p = JevActionPlanner(provider=None)
    p._battle, p._entity, p._session, p._map = battle, entity, session, battle_map
    p._names = p._display_names(battle, entity)
    return p


class TestJevRespectsAvailableActions:
    def test_polymorphed_caster_gets_no_spell_leaves(self, world):
        session, battle_map, battle = world
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        goblin = session.npc('goblin')
        battle.add(mage, 'a', position=(1, 5), token='M')
        battle.add(goblin, 'b', position=(2, 5), token='g')
        _start(battle, mage, goblin)
        polymorph.transform(mage, 'cat', battle=battle)

        leaves = _planner(session, battle, battle_map, mage)._collect_leaves(None)

        assert not [a for t, a, _ in leaves if t == 'spell']
        attacks = [a for t, a, _ in leaves if t == 'attack' and a.target is goblin]
        assert attacks, 'the beast form should still attack with its own statblock'

    def test_cunning_action_hide_is_offered(self, world):
        session, battle_map, battle = world
        goblin = session.npc('goblin')
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(goblin, 'b', position=(1, 5), token='g')
        battle.add(fighter, 'a', position=(5, 5), token='F')
        _start(battle, goblin, fighter)

        leaves = _planner(session, battle, battle_map, goblin)._collect_leaves(None)

        hides = [(a, d) for _, a, d in leaves if isinstance(a, HideBonusAction)]
        assert hides
        assert 'hide after shooting' in hides[0][1]


class TestPointlessActions:
    def test_second_wind_at_full_hp_is_dropped(self, world):
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        _start(battle, fighter)
        sw = SecondWindAction(session, fighter, 'second_wind')
        assert pointless_actions.filter_actions(battle, fighter, [sw]) == []
        fighter.attributes['hp'] = fighter.max_hp() - 5
        assert pointless_actions.filter_actions(battle, fighter, [sw]) == [sw]

    def test_looting_with_an_enemy_in_sight_is_dropped(self, world):
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(goblin, 'b', position=(3, 5), token='g')
        _start(battle, fighter, goblin)
        loot = InteractAction(session, fighter, 'interact',
                              {'target': MagicMock(), 'object_action': 'loot'})
        assert pointless_actions.filter_actions(battle, fighter, [loot]) == []
        goblin.attributes['hp'] = 0
        goblin.make_dead()
        assert pointless_actions.filter_actions(battle, fighter, [loot]) == [loot]

    def test_look_with_every_enemy_visible_is_dropped(self, world):
        from natural20.actions.look_action import LookAction
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(goblin, 'b', position=(3, 5), token='g')
        _start(battle, fighter, goblin)
        look = LookAction(session, fighter, 'look')
        assert pointless_actions.filter_actions(battle, fighter, [look]) == []
        goblin.do_hide(30)
        assert pointless_actions.filter_actions(battle, fighter, [look]) == [look]

    def test_look_at_an_invisible_but_unhidden_enemy_is_dropped(self, world):
        from natural20.actions.look_action import LookAction
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(goblin, 'b', position=(3, 5), token='g')
        _start(battle, fighter, goblin)
        goblin.statuses.append('invisible')
        look = LookAction(session, fighter, 'look')
        assert pointless_actions.filter_actions(battle, fighter, [look]) == []

    def test_looting_while_an_invisible_enemy_is_around_is_dropped(self, world):
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(goblin, 'b', position=(3, 5), token='g')
        _start(battle, fighter, goblin)
        goblin.statuses.append('invisible')
        loot = InteractAction(session, fighter, 'interact',
                              {'target': MagicMock(), 'object_action': 'loot'})
        assert pointless_actions.filter_actions(battle, fighter, [loot]) == []

    def test_action_surge_only_after_the_action_is_spent(self, world):
        from natural20.actions.action_surge_action import ActionSurgeAction
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(goblin, 'b', position=(2, 5), token='g')
        _start(battle, fighter, goblin)
        surge = ActionSurgeAction(session, fighter, 'action_surge')
        assert pointless_actions.filter_actions(battle, fighter, [surge]) == []
        battle.entity_state_for(fighter)['action'] = 0
        assert pointless_actions.filter_actions(battle, fighter, [surge]) == [surge]

    def test_disengage_only_when_threatened_in_melee(self, world):
        from natural20.actions.disengage_action import DisengageAction
        session, battle_map, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(goblin, 'b', position=(3, 5), token='g')
        _start(battle, fighter, goblin)
        disengage = DisengageAction(session, fighter, 'disengage')
        assert pointless_actions.filter_actions(battle, fighter, [disengage]) == []
        battle_map.move_to(goblin, 2, 5, battle)
        assert pointless_actions.filter_actions(battle, fighter, [disengage]) == [disengage]

    def test_help_on_self_or_an_able_ally_is_dropped(self, world):
        from natural20.actions.help_action import HelpAction
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(mage, 'a', position=(1, 6), token='M')
        battle.add(goblin, 'b', position=(2, 5), token='g')
        _start(battle, fighter, mage, goblin)

        def helping(target):
            action = HelpAction(session, fighter, 'help')
            action.target = target
            return action

        assert pointless_actions.is_pointless(battle, fighter, helping(fighter))
        assert pointless_actions.is_pointless(battle, fighter, helping(mage))
        assert not pointless_actions.is_pointless(battle, fighter, helping(goblin))
        mage.statuses.append('sleep')
        assert not pointless_actions.is_pointless(battle, fighter, helping(mage))


class TestSightBasedAbilities:
    def test_force_hit_and_no_damage_abilities_cannot_be_aimed_blind(self):
        from natural20.utils.unseen_targets import makes_attack_roll
        assert not makes_attack_roll(SimpleNamespace(npc_action={'name': 'Charm', 'no_damage': True}))
        assert not makes_attack_roll(SimpleNamespace(npc_action={'name': 'Gaze', 'force_hit': True}))
        assert makes_attack_roll(SimpleNamespace(npc_action={'name': 'Claw'}))
        source = SimpleNamespace(npc_actions=[{'name': 'Charm', 'no_damage': True}])
        assert not makes_attack_roll(SimpleNamespace(npc_action=None, using='charm', source=source))


class TestConcentrationReplaced:
    def test_new_concentration_spell_ends_the_old_one_even_if_target_saves(self, world):
        session, battle_map, battle = world
        caster = PlayerCharacter.load(session, 'high_elf_mage.yml')
        first = session.npc('goblin', {'name': 'First'})
        second = session.npc('goblin', {'name': 'Second'})
        battle.add(caster, 'a', position=(0, 0), token='M')
        battle.add(first, 'b', position=(0, 2), token='f')
        battle.add(second, 'b', position=(2, 2), token='s')
        _start(battle, caster, first, second)

        def cast(target, save_total):
            roll = SimpleNamespace(result=lambda: save_total, prob=lambda dc: 0.5)
            target.save_throw = lambda *a, **k: roll
            action = SpellAction(session, caster, 'spell')
            action.spell_action = PolymorphSpell(session, caster, 'polymorph',
                                                 session.load_spell('polymorph'))
            action.spell_action.action = action
            action.target = target
            action.skip_consume_at_resolve = True
            action.resolve(session, battle_map, {'battle': battle})
            for item in action.result:
                SpellAction.apply(battle, item, session)
            return action

        held = cast(first, save_total=1).spell_action
        assert caster.current_concentration() is held
        assert polymorph.is_polymorphed(first)

        cast(second, save_total=30)

        assert caster.current_concentration() is None
        assert not polymorph.is_polymorphed(first)
        assert not polymorph.is_polymorphed(second)


class TestMovementJitter:
    def _duel(self, world, goblin_pos=(1, 5), fighter_pos=(2, 5)):
        session, battle_map, battle = world
        goblin = session.npc('goblin')
        goblin.properties['attributes'] = [
            a for a in goblin.properties.get('attributes', []) if a != 'nimble_escape']
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(goblin, 'b', position=goblin_pos, token='g')
        battle.add(fighter, 'a', position=fighter_pos, token='F')
        _start(battle, goblin, fighter)
        return session, battle_map, battle, goblin, fighter

    def test_entering_then_leaving_reach_provokes(self, world):
        _, _, battle, goblin, _ = self._duel(world, goblin_pos=(0, 5), fighter_pos=(2, 5))
        assert _oa_risk(battle, goblin, [(0, 5), (1, 5), (0, 6)])

    def test_no_shuffling_around_a_foe_after_acting(self, world):
        session, battle_map, battle, goblin, _ = self._duel(world)
        battle.entity_state_for(goblin)['action'] = 0
        leaves = list(_planner(session, battle, battle_map, goblin)._move_leaves())
        assert not [d for _, d in leaves if 'engage' in d or 'offensive' in d]

    def test_no_return_to_turn_start_square(self, world):
        session, battle_map, battle, goblin, _ = self._duel(world, fighter_pos=(5, 5))
        battle.entity_state_for(goblin)['turn_start_position'] = [1, 6]
        leaves = list(_planner(session, battle, battle_map, goblin)._move_leaves())
        assert leaves
        assert all(tuple(a.move_path[-1]) != (1, 6) for a, _ in leaves)

    def test_healthy_creature_does_not_provoke(self, world):
        session, battle_map, battle, goblin, fighter = self._duel(world)
        leaves = list(_planner(session, battle, battle_map, goblin)._move_leaves())
        assert all(not _oa_risk(battle, goblin, a.move_path) for a, _ in leaves)


class TestCalloutMenu:
    def _party(self, world, foes=1):
        session, _, battle = world
        gruk = session.npc('goblin', {'name': 'Gruk'})
        snix = session.npc('goblin', {'name': 'Snix'})
        battle.add(gruk, 'b', position=(2, 2), token='g')
        battle.add(snix, 'b', position=(3, 2), token='G')
        enemies = [PlayerCharacter.load(session, 'high_elf_fighter.yml')]
        battle.add(enemies[0], 'a', position=(4, 3), token='F')
        if foes > 1:
            enemies.append(PlayerCharacter.load(session, 'high_elf_mage.yml'))
            battle.add(enemies[1], 'a', position=(5, 3), token='M')
        _start(battle, gruk, snix, *enemies)
        return battle, gruk, snix, enemies

    def test_no_focus_fire_against_a_lone_foe(self, world):
        battle, gruk, _, (fighter,) = self._party(world)
        fighter.attributes['hp'] = 5
        kinds = {o['kind'] for o in strategy_options(battle, gruk, MagicMock(target=fighter))}
        assert 'focus' not in kinds

    def test_finish_off_only_for_a_truly_wounded_foe(self, world):
        battle, gruk, _, (fighter, mage) = self._party(world, foes=2)
        fighter.attributes['hp'] = fighter.max_hp() - 1
        descs = [o['desc'] for o in strategy_options(battle, gruk)]
        assert not any('most wounded' in d for d in descs)

    def test_fallen_ally_prompts_revive_and_regroup_first(self, world):
        battle, gruk, snix, (fighter, mage) = self._party(world, foes=2)
        snix.attributes['hp'] = 0
        snix.make_unconscious()
        opts = strategy_options(battle, gruk, MagicMock(target=fighter))
        kinds = [o['kind'] for o in opts[1:]]
        assert kinds[0] == 'revive' and opts[1]['target'] is snix
        assert 'regroup' in kinds
        assert kinds.index('regroup') < kinds.index('focus')


class TestLogNoise:
    def test_damage_to_a_dead_creature_does_not_kill_it_again(self, world):
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        _start(battle, fighter)
        fighter.attributes['hp'] = 0
        fighter.make_dead()
        fighter.make_dead = MagicMock()
        fighter.take_damage(fighter.max_hp() * 3, battle=battle, damage_type='necrotic')
        fighter.make_dead.assert_not_called()

    def test_area_saves_skip_standing_walls(self, world):
        from natural20.item_library.common import StoneWall
        from natural20.spell.extensions.save_for_half import SaveForHalfMixin
        from natural20.die_roll import DieRoll
        session, _, battle = world
        goblin = session.npc('goblin')
        wall = StoneWall(session, None, {'name': 'Wall', 'max_hp': 27, 'default_ac': 17})
        caster = SimpleNamespace(source=None, properties={})
        results = SaveForHalfMixin.resolve_save_for_half(
            caster, [wall, goblin], ability='dexterity', dc=15,
            damage_roll=DieRoll.roll('8d6'), attack_name='fireball',
            damage_type='fire', battle=None)
        assert [r['target'] for r in results] == [goblin]


class TestMovementAfterActing:
    def _descs(self, session, battle, battle_map, entity):
        return [d for _, _, d in _planner(session, battle, battle_map, entity)._collect_leaves(None)]

    def test_retreat_is_offered_after_disengaging(self, world):
        from natural20.actions.disengage_action import DisengageAction
        session, battle_map, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(2, 5), token='F')
        battle.add(goblin, 'b', position=(1, 5), token='g')
        _start(battle, goblin, fighter)
        action = DisengageAction(session, goblin, 'disengage')
        battle.action(action)
        battle.commit(action)
        descs = self._descs(session, battle, battle_map, goblin)
        assert any(d.startswith('move: retreat to') for d in descs), descs

    def test_caster_does_not_walk_into_melee_after_acting(self, world):
        session, battle_map, battle = world
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        goblin = session.npc('goblin')
        battle.add(mage, 'a', position=(5, 6), token='M')
        battle.add(goblin, 'b', position=(1, 5), token='g')
        _start(battle, mage, goblin)
        battle.entity_state_for(mage)['action'] = 0
        descs = self._descs(session, battle, battle_map, mage)
        assert not any('engage' in d or 'offensive' in d for d in descs), descs


class TestAttackOdds:
    def test_attack_leaves_show_disadvantage_and_hit_chance(self, world):
        session, battle_map, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(2, 5), token='F')
        battle.add(goblin, 'b', position=(1, 5), token='g')
        _start(battle, fighter, goblin)
        descs = [d for t, _, d in _planner(session, battle, battle_map, fighter)._collect_leaves(None)
                 if t == 'attack' and 'unseen' not in d]
        assert descs and all('% hit' in d for d in descs), descs
        ranged = [d for d in descs if 'bow' in d.lower()]
        assert all('disadvantage' in d for d in ranged), ranged


class TestNonCombatSpells:
    def test_ai_in_combat_false_spells_are_dropped_mid_fight(self, world):
        session, _, battle = world
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        goblin = session.npc('goblin')
        battle.add(mage, 'a', position=(1, 5), token='M')
        battle.add(goblin, 'b', position=(3, 5), token='g')
        _start(battle, mage, goblin)
        utility = SimpleNamespace(spell_action=SimpleNamespace(properties={'ai_in_combat': False}))
        combat = SimpleNamespace(spell_action=SimpleNamespace(properties={'damage_type': 'fire'}))
        assert pointless_actions.is_pointless(battle, mage, utility)
        assert not pointless_actions.is_pointless(battle, mage, combat)
        goblin.attributes['hp'] = 0
        goblin.make_dead()
        assert not pointless_actions.is_pointless(battle, mage, utility)


class TestDeathLog:
    def test_massive_damage_death_is_logged_once(self, world):
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        _start(battle, fighter)
        lines = []
        session.event_manager.output_logger = SimpleNamespace(log=lines.append)
        session.event_manager.standard_cli()
        fighter.take_damage(fighter.max_hp() * 3, battle=battle, damage_type='necrotic')
        assert fighter.dead()
        deaths = [l for l in lines if 'died' in l]
        assert len(deaths) == 1 and 'instantly' in deaths[0], lines


class TestStalemate:
    def test_far_foe_gets_an_advance_leaf(self):
        random.seed(7000)
        session = Session(root_path='tests/fixtures', event_manager=EventManager())
        battle_map = Map(session, 'large_map')
        battle = Battle(session, battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 6), token='F')
        battle.add(goblin, 'b', position=(28, 6), token='g')
        _start(battle, goblin, fighter)
        descs = [d for _, _, d in _planner(session, battle, battle_map, goblin)._collect_leaves(None)]
        assert any(d.startswith('move: advance toward') for d in descs), descs

    def test_dash_is_pointless_without_a_known_enemy_position(self, world):
        from natural20.actions.dash import DashAction
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(goblin, 'b', position=(4, 5), token='g')
        _start(battle, goblin, fighter)
        dash = DashAction(session, goblin, 'dash')
        fighter.do_hide(40)
        assert not battle.can_see(goblin, fighter)
        assert pointless_actions.is_pointless(battle, goblin, dash)
        fighter.break_stealth()
        # The fighter is within this turn's movement: Dash buys nothing.
        assert pointless_actions.is_pointless(battle, goblin, dash)
        battle.entity_state_for(goblin)['movement'] = 0
        assert not pointless_actions.is_pointless(battle, goblin, dash)

    def test_dash_still_allowed_to_flee_when_hurt(self, world):
        from natural20.actions.dash import DashAction
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(goblin, 'b', position=(4, 5), token='g')
        _start(battle, goblin, fighter)
        goblin.attributes['hp'] = 1
        assert not pointless_actions.is_pointless(battle, goblin, DashAction(session, goblin, 'dash'))

    def test_jev_must_move_after_dashing(self, world):
        session, battle_map, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(0, 6), token='F')
        battle.add(goblin, 'b', position=(5, 0), token='g')
        _start(battle, goblin, fighter)
        planner = _planner(session, battle, battle_map, goblin)
        assert any(t == 'end_turn' for t, _, _ in planner._collect_leaves(None))
        battle.entity_state_for(goblin)['movement'] += goblin.speed()
        leaves = planner._collect_leaves(None)
        assert any(t == 'move' for t, _, _ in leaves)
        assert not any(t == 'end_turn' for t, _, _ in leaves)


class TestAreaTargeting:
    def test_hidden_foes_do_not_attract_area_spells(self, world):
        from natural20.utils.action_builder import _optimize_radius_targets
        session, battle_map, battle = world
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        goblin = session.npc('goblin')
        battle.add(mage, 'a', position=(1, 5), token='M')
        battle.add(goblin, 'b', position=(4, 5), token='g')
        _start(battle, mage, goblin)
        choices = [[4, 5]]
        goblin.do_hide(40)
        assert _optimize_radius_targets(choices, mage, battle, battle_map, 0) == []
        goblin.break_stealth()
        assert _optimize_radius_targets(choices, mage, battle, battle_map, 0) == [[4, 5]]

    def test_downed_foes_count_for_half(self, world):
        from natural20.utils.action_builder import _score_squares
        session, battle_map, battle = world
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        goblin = session.npc('goblin')
        battle.add(mage, 'a', position=(1, 5), token='M')
        battle.add(goblin, 'b', position=(4, 5), token='g')
        _start(battle, mage, goblin)
        assert _score_squares([(4, 5)], mage, battle, battle_map) == 1
        goblin.make_unconscious()
        assert _score_squares([(4, 5)], mage, battle, battle_map) == 0.5
        goblin.make_dead()
        assert _score_squares([(4, 5)], mage, battle, battle_map) == 0


class TestLogText:
    def test_flat_bonus_has_no_phantom_die(self):
        from natural20.die_roll import DieRoll
        assert str(DieRoll.roll('+1')) == '1'
        assert 'd0' not in str(DieRoll.roll('1d20+4') + DieRoll.roll('+1'))

    def test_damage_without_a_roll_is_logged_plainly(self, world):
        session, _, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        _start(battle, fighter)
        lines = []
        session.event_manager.output_logger = SimpleNamespace(log=lines.append)
        session.event_manager.standard_cli()
        session.event_manager.received_event({'source': fighter, 'event': 'damage', 'roll_info': None,
                                              'value': 12, 'total_damage': 12, 'damage_type': 'fire'})
        assert any(l.endswith('took 12 fire damage.') for l in lines), lines


class TestDownedTargets:
    def _setup(self, world):
        session, battle_map, battle = world
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        goblin = session.npc('goblin')
        battle.add(fighter, 'a', position=(1, 5), token='F')
        battle.add(mage, 'a', position=(3, 5), token='M')
        battle.add(goblin, 'b', position=(2, 5), token='g')
        _start(battle, goblin, fighter, mage)
        return session, battle, fighter, mage, goblin

    def _attack(self, session, goblin, target):
        action = AttackAction(session, goblin, 'attack')
        action.npc_action = next(a for a in goblin.npc_actions if a['name'] == 'Scimitar')
        action.target = target
        return action

    def test_attacks_on_downed_foes_wait_while_others_stand(self, world):
        session, battle, fighter, mage, goblin = self._setup(world)
        fighter.make_unconscious()
        on_downed = self._attack(session, goblin, fighter)
        on_mage = self._attack(session, goblin, mage)
        kept = pointless_actions.filter_actions(battle, goblin, [on_downed, on_mage])
        assert kept == [on_mage]
        assert on_downed.ai_value(battle) < on_mage.ai_value(battle)
        assert pointless_actions.filter_actions(battle, goblin, [on_downed]) == [on_downed]
        goblin.properties['finish_downed'] = True
        assert pointless_actions.filter_actions(battle, goblin, [on_downed, on_mage]) == [on_downed, on_mage]

    def test_spare_the_dying_gives_way_to_a_real_heal(self, world):
        session, battle, fighter, mage, goblin = self._setup(world)
        fighter.make_unconscious()
        spare = SimpleNamespace(spell_action=SimpleNamespace(properties={'type': 'healing', 'level': 0}),
                                target=fighter)
        heal = SimpleNamespace(spell_action=SimpleNamespace(properties={'type': 'healing', 'level': 1}),
                               target=fighter)
        assert pointless_actions.filter_actions(battle, mage, [spare, heal]) == [heal]
        assert pointless_actions.filter_actions(battle, mage, [spare]) == [spare]

    def test_dash_while_in_melee_is_pointless(self, world):
        from natural20.actions.dash import DashAction
        session, battle, fighter, mage, goblin = self._setup(world)
        assert pointless_actions.is_pointless(battle, mage, DashAction(session, mage, 'dash'))
        mage.attributes['hp'] = 1
        assert not pointless_actions.is_pointless(battle, mage, DashAction(session, mage, 'dash'))


class TestRangedCombatantsInMelee:
    def test_engaged_caster_is_offered_a_retreat_through_an_opportunity_attack(self, world):
        session, battle_map, battle = world
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        goblin = session.npc('goblin')
        battle.add(mage, 'a', position=(2, 5), token='M')
        battle.add(goblin, 'b', position=(1, 5), token='g')
        _start(battle, mage, goblin)
        descs = [d for _, _, d in _planner(session, battle, battle_map, mage)._collect_leaves(None)]
        assert any(d.startswith('move: retreat to') and 'opportunity attack' in d for d in descs), descs

    def test_skirmisher_does_not_walk_into_melee_after_shooting(self, world):
        session, battle_map, battle = world
        rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
        goblin = session.npc('goblin')
        battle.add(rogue, 'a', position=(5, 5), token='R')
        battle.add(goblin, 'b', position=(1, 5), token='g')
        _start(battle, rogue, goblin)
        battle.entity_state_for(rogue)['action'] = 0
        descs = [d for _, _, d in _planner(session, battle, battle_map, rogue)._collect_leaves(None)]
        assert not any('engage' in d or 'offensive' in d or 'advance' in d for d in descs), descs


class TestReadableAttackLog:
    def test_attack_names_and_advantage_are_humanized(self):
        from natural20.utils.attack_util import to_advantage_str
        em = EventManager()
        assert em.attack_label('spell.guiding_bolt') == 'Guiding Bolt'
        assert em.attack_label('unarmed_strike2') == 'Unarmed Strike'
        assert em.attack_label('Rapier') == 'Rapier'
        event = {'adv_info': [['target_is_prone'], []], 'advantage_mod': 1}
        assert to_advantage_str(event) == ' with advantage (target is prone)'
