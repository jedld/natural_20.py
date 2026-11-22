"""Regressions for the rules bugs reported in GitHub issue #6.

Each test mirrors a divergence found while replaying engine fights ("dice
tapes") against a second implementation. Grouped by the issue's sections:
dice and rolls, combat rules, spells, heuristic AI, and 2024 ruleset data.
"""

import random
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from natural20.actions.attack_action import AttackAction
from natural20.actions.hide_action import HideAction
from natural20.actions.move_action import MoveAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.item_library.common import Ground
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.bless_spell import BlessSpell
from natural20.spell.magic_missile_spell import MagicMissileSpell
from natural20.spell.mage_armor_spell import MageArmorSpell
from natural20.spell.ray_of_frost_spell import RayOfFrostSpell
from natural20.spell.shield_of_faith_spell import ShieldOfFaithSpell
from natural20.spell.shield_spell import ShieldSpell
from natural20.utils.action_builder import _score_squares
from natural20.utils.spell_attack_util import spell_attack_is_critical


def _session(events=None):
    em = EventManager()
    em.standard_cli()
    session = Session(root_path='tests/fixtures', event_manager=em)
    if events is not None:
        original = em.received_event

        def record(event):
            events.append(event)
            return original(event)
        em.received_event = record
    return session


class DieParsingTest(unittest.TestCase):
    def test_fixed_value_with_negative_modifier(self):
        """An unarmed strike at STR 8 parses as 1, then a -1 modifier."""
        detail = DieRoll.parse("1-1")
        self.assertEqual(detail.die_count, 1)
        self.assertFalse(detail.die_type)
        self.assertEqual(DieRoll.modifier_value(detail.modifier_op, detail.modifier), -1)
        self.assertEqual(DieRoll.roll("1-1").result(), 0)

    def test_negative_roll_modifier(self):
        detail = DieRoll.parse("1d20-2")
        self.assertEqual(detail.die_type, "20")
        self.assertEqual(DieRoll.modifier_value(detail.modifier_op, detail.modifier), -2)

    def test_d20_helper_formats_negative_modifier(self):
        """Roll strings built as f"1d20+{mod}" produced "1d20+-2", which read
        back as +2: a zombie with -2 initiative rolled as if it were +2."""
        self.assertEqual(DieRoll.d20(-2), "1d20-2")
        self.assertEqual(DieRoll.d20(2), "1d20+2")
        self.assertEqual(DieRoll.d20(0), "1d20+0")
        roll = DieRoll.roll(DieRoll.d20(-2))
        self.assertTrue(-1 <= roll.result() <= 18)
        self.assertEqual(roll.modifier, -2)


class AttackSpellScoringTest(unittest.TestCase):
    """Issue 17 (attack side): hit-chance / mean-damage scoring for attack
    spells must be analytic, not sampled from the game RNG."""

    def test_scoring_draws_no_dice(self):
        from natural20.spell.firebolt_spell import FireboltSpell

        random.seed(77)
        session = _session()
        map_ = Map(session, 'battle_sim')
        battle = Battle(session, map_)
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        foe = session.npc('skeleton')
        battle.add(mage, 'a', position=[0, 5])
        battle.add(foe, 'b', position=[2, 5])
        battle.start(combat_order=[mage, foe])
        spell = FireboltSpell(session, mage, 'firebolt', session.load_spell('firebolt'))
        spell.action = SimpleNamespace(target=foe, at_level=1)
        before = random.getstate()
        hit = spell.compute_hit_probability(battle)
        damage = spell.avg_damage(battle)
        self.assertEqual(random.getstate(), before)
        self.assertTrue(0.0 < hit < 1.0, f"hit chance {hit}")
        self.assertGreater(damage, 0)
        # Deterministic: same call, same numbers.
        self.assertEqual(spell.compute_hit_probability(battle), hit)
        self.assertEqual(spell.avg_damage(battle), damage)


class EstimateTest(unittest.TestCase):
    """AI hit-chance and mean-damage estimates must not touch the game RNG."""

    def test_estimates_draw_no_dice_and_are_exact(self):
        before = random.getstate()
        estimate = DieRoll.estimate("2d6+3")
        self.assertEqual(random.getstate(), before)
        self.assertEqual(estimate.expected(), 3.5 * 2 + 3)
        self.assertEqual(DieRoll.estimate(DieRoll.d20(-2)).expected(), 10.5 - 2)

    def test_estimated_probabilities_are_analytic(self):
        self.assertEqual(DieRoll.estimate(DieRoll.d20(5)).prob(16), 0.5)
        self.assertAlmostEqual(
            DieRoll.estimate(DieRoll.d20(5), advantage=True).prob(16),
            1 - (10 / 20) ** 2,
        )

    def test_repeated_estimates_do_not_shift_later_dice(self):
        """Option scoring used to roll real dice, so adding an option that is
        never picked still changed every later roll in the fight."""
        random.seed(1234)
        baseline = DieRoll.roll("1d20+4").result()

        random.seed(1234)
        for _ in range(25):
            DieRoll.estimate("1d20+4").prob(15)
            DieRoll.estimate("2d6+2").expected()
        self.assertEqual(DieRoll.roll("1d20+4").result(), baseline)


class AdvantageDiceTest(unittest.TestCase):
    def test_advantage_dice_are_independent(self):
        """The pair used to come from random.sample, so equal values (double
        natural 1 with advantage, double natural 20 with disadvantage) were
        impossible."""
        from collections import Counter

        random.seed(99)
        pairs = [tuple(DieRoll.generate_number(20, advantage=True)) for _ in range(500)]
        doubles = Counter(p for p in pairs if p[0] == p[1])
        self.assertTrue(doubles, "advantage dice never came up equal")
        self.assertTrue(any(p[0] == 20 for p in pairs))
        self.assertTrue(any(p[0] == 1 for p in pairs))


class SaveAdvantageCancellationTest(unittest.TestCase):
    """Advantage and disadvantage on the same roll cancel out."""

    def setUp(self):
        from natural20.session import Session
        from natural20.player_character import PlayerCharacter

        self.session = Session(root_path='tests/fixtures')
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

    def test_advantage_and_disadvantage_cancel(self):
        roll = self.fighter.save_throw(
            'strength',
            opts={'advantage': ['magic_resistance'], 'disadvantage': ['restrained']},
        )
        self.assertFalse(roll.advantage)
        self.assertFalse(roll.disadvantage)
        self.assertFalse(any(isinstance(entry, (tuple, list)) for entry in roll.rolls))

    def test_advantage_alone_still_applies(self):
        roll = self.fighter.save_throw('strength', opts={'advantage': ['magic_resistance']})
        self.assertTrue(roll.advantage)
        self.assertFalse(roll.disadvantage)

    def test_disadvantage_alone_still_applies(self):
        roll = self.fighter.save_throw('strength', opts={'disadvantage': ['restrained']})
        self.assertFalse(roll.advantage)
        self.assertTrue(roll.disadvantage)


class ConcentrationAndEffectTest(unittest.TestCase):
    """Dropping concentration or falling over must not vaporize unrelated
    effects (issues 5, 6 and 16)."""

    def setUp(self):
        self.events = []
        self.session = _session(self.events)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.cleric_a = PlayerCharacter.load(self.session, 'high_elf_mage.yml', {'name': 'Cleric A'})
        self.cleric_b = PlayerCharacter.load(self.session, 'high_elf_mage.yml', {'name': 'Cleric B'})
        self.ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.map.add(self.cleric_a, 0, 0)
        self.map.add(self.cleric_b, 0, 1)
        self.map.add(self.ally, 1, 0)
        self.battle.add(self.cleric_a, 'a', add_to_initiative=True)
        self.battle.add(self.cleric_b, 'a', add_to_initiative=True)
        self.battle.add(self.ally, 'a', add_to_initiative=True)
        self.battle.start(combat_order=[self.cleric_a, self.cleric_b, self.ally])
        self.ally.reset_turn(self.battle)

    def _bless(self, caster):
        spell = BlessSpell(self.session, caster, 'bless', self.session.load_spell('bless'))
        spell.action = SimpleNamespace(target=self.ally, at_level=1)
        for item in spell.resolve(caster, self.battle, spell.action, self.map):
            BlessSpell.apply(self.battle, item, self.session)
        self.assertEqual(caster.current_concentration(), spell)
        return spell

    def test_two_casts_of_the_same_spell_are_independent(self):
        """Two clerics Bless the same ally: ending one cast must leave the
        other standing. `Spell.id` is the shared YAML id, so matching by id
        removed both."""
        spell_a = self._bless(self.cleric_a)
        spell_b = self._bless(self.cleric_b)

        self.cleric_a.dismiss_effect(spell_a)

        self.assertTrue(self.ally.has_effect('bless'))
        remaining = [e for e in self.ally.effects.get('bless', [])]
        self.assertEqual(len(remaining), 1)
        self.assertIs(remaining[0]['effect'], spell_b)
        self.assertTrue(self.cleric_b.has_effect('bless') or
                        self.cleric_b.current_concentration() is spell_b)

    def test_unconscious_caster_only_loses_concentration(self):
        """A caster dropping to 0 HP keeps the non-concentration effects they
        cast (Aid's hit-point boost, Sanctuary, ...)."""
        bless = self._bless(self.cleric_a)
        extra = BlessSpell(self.session, self.cleric_a, 'bless', self.session.load_spell('bless'))
        extra.action = SimpleNamespace(target=self.ally, at_level=1)
        self.cleric_a.add_casted_effect({'target': self.ally, 'effect': extra})
        self.ally.register_effect('bless', BlessSpell, effect=extra, source=self.cleric_a,
                                  duration=60)

        self.cleric_a.attributes['hp'] = 0
        self.cleric_a.make_unconscious()

        self.assertTrue(self.cleric_a.unconscious())
        self.assertIsNone(self.cleric_a.current_concentration())
        # The concentrating cast ends...
        self.assertFalse([e for e in self.ally.effects.get('bless', [])
                          if e['effect'] is bless])
        # ...but the caster's other cast still stands.
        self.assertIn(extra, [e.get('effect') for e in self.cleric_a.casted_effects])
        self.assertTrue([e for e in self.ally.effects.get('bless', [])
                         if e['effect'] is extra])

    def test_dead_caster_only_loses_concentration(self):
        bless = self._bless(self.cleric_a)
        extra = BlessSpell(self.session, self.cleric_a, 'bless', self.session.load_spell('bless'))
        extra.action = SimpleNamespace(target=self.ally, at_level=1)
        self.cleric_a.add_casted_effect({'target': self.ally, 'effect': extra})

        self.cleric_a.make_dead()
        self.assertTrue(self.cleric_a.dead())
        self.assertIsNone(self.cleric_a.current_concentration())
        self.assertIn(extra, [e.get('effect') for e in self.cleric_a.casted_effects])


class AcBonusStackingTest(unittest.TestCase):
    """AC bonuses from separate sources add up (issue 7)."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.map.add(self.mage, 0, 0)
        self.battle.add(self.mage, 'a', add_to_initiative=True)
        self.battle.start(combat_order=[self.mage])

    def test_shield_and_shield_of_faith_both_count(self):
        base = self.mage.armor_class()
        shield = ShieldSpell(self.session, self.mage, 'shield', self.session.load_spell('shield'))
        faith = ShieldOfFaithSpell(self.session, self.mage, 'shield_of_faith',
                                   self.session.load_spell('shield_of_faith'))
        self.mage.register_effect('ac_bonus', ShieldSpell, effect=shield, source=self.mage,
                                  duration=8 * 60 * 60)
        self.mage.register_effect('ac_bonus', ShieldOfFaithSpell, effect=faith, source=self.mage,
                                  duration=8 * 60 * 60)
        self.assertEqual(self.mage.armor_class(), base + 5 + 2)

    def test_removing_one_leaves_the_other(self):
        base = self.mage.armor_class()
        shield = ShieldSpell(self.session, self.mage, 'shield', self.session.load_spell('shield'))
        faith = ShieldOfFaithSpell(self.session, self.mage, 'shield_of_faith',
                                   self.session.load_spell('shield_of_faith'))
        self.mage.register_effect('ac_bonus', ShieldSpell, effect=shield, source=self.mage,
                                  duration=8 * 60 * 60)
        self.mage.register_effect('ac_bonus', ShieldOfFaithSpell, effect=faith, source=self.mage,
                                  duration=8 * 60 * 60)
        self.mage.remove_effect(shield)
        self.assertEqual(self.mage.armor_class(), base + 2)


class NpcDamageModTest(unittest.TestCase):
    """NPC YAML ``damage_mod`` is added to the damage die (issue 9)."""

    def setUp(self):
        self.session = _session()
        self.goblin = self.session.npc('goblin')

    def test_shortbow_damage_includes_flat_bonus(self):
        action = AttackAction(self.session, self.goblin, 'attack')
        shortbow = next(a for a in self.goblin.properties['actions'] if a['name'] == 'Shortbow')
        _, _, _, damage_roll, _ = action.get_weapon_info({'npc_action': shortbow})
        self.assertEqual(damage_roll, '1d6+2')

    def test_damage_die_already_including_bonus_is_untouched(self):
        action = AttackAction(self.session, self.goblin, 'attack')
        npc_action = {'name': 'Bite', 'type': 'melee_attack', 'range': 5, 'targets': 1,
                      'attack': 4, 'damage': 7, 'damage_die': '1d6+2', 'damage_mod': 2,
                      'damage_type': 'piercing'}
        _, _, _, damage_roll, _ = action.get_weapon_info({'npc_action': npc_action})
        self.assertEqual(damage_roll, '1d6+2')


class ThrownWeaponDroppedTest(unittest.TestCase):
    """A thrown weapon lands in the target's space, not its inventory
    (issue 30)."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.attacker = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.target = PlayerCharacter.load(self.session, 'high_elf_fighter.yml', {'name': 'Target'})
        self.map.add(self.attacker, 0, 0)
        self.map.add(self.target, 2, 0)
        self.battle.add(self.attacker, 'a', add_to_initiative=True)
        self.battle.add(self.target, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.attacker, self.target])

    def test_hit_leaves_dagger_on_the_ground(self):
        self.attacker.add_item('dagger', 2)
        self.attacker.equip('dagger')
        before = self.attacker.item_count('dagger')
        action = AttackAction(self.session, self.attacker, 'attack')
        action.using = 'dagger'
        action.thrown = True
        action.target = self.target
        item = {
            'type': 'damage',
            'source': self.attacker,
            'target': self.target,
            'weapon': 'dagger',
            'thrown': True,
            'second_hand': False,
            'battle': self.battle,
        }
        AttackAction.consume_resource(self.battle, item)

        self.assertEqual(self.target.item_count('dagger'), 0)
        ground = [obj for obj in self.map.objects_at(2, 0) if isinstance(obj, Ground)]
        self.assertTrue(ground, "no ground object where the weapon should have landed")
        inventories = [obj.inventory for obj in ground]
        self.assertTrue(any('dagger' in (inv or {}) for inv in inventories),
                        f"dagger not on the ground: {inventories}")
        self.assertEqual(self.attacker.item_count('dagger'), before - 1)


class SapDirectionTest(unittest.TestCase):
    """SRD 5.2.1 Sap marks the *target* of the hit, and the disadvantage
    applies to that creature's next attack — not to the Sap wielder
    (issue 24)."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.fighter, 'a', position=[0, 0])
        self.battle.add(self.goblin, 'b', position=[1, 0])
        self.battle.start(combat_order=[self.fighter, self.goblin])
        # The engine's Sap marker: set on the creature that was hit.
        self.goblin._sap_next_attack = True

    def _advantages(self, source, target, weapon):
        from natural20.weapons import compute_advantages_and_disadvantages
        return compute_advantages_and_disadvantages(
            self.session, source, target, weapon, battle=self.battle)

    def test_sapped_creature_attacks_with_disadvantage(self):
        _adv, dis = self._advantages(self.goblin, self.fighter, 'dagger')
        self.assertIn('weapon_mastery_sap', dis)
        # The marker is consumed by that one attack.
        _adv, dis = self._advantages(self.goblin, self.fighter, 'dagger')
        self.assertNotIn('weapon_mastery_sap', dis)

    def test_sap_wielder_is_never_handicapped(self):
        _adv, dis = self._advantages(self.fighter, self.goblin, 'longsword')
        self.assertNotIn('weapon_mastery_sap', dis)
        # The sapped marker must survive the wielder's own attacks.
        self.assertTrue(self.goblin._sap_next_attack)


class StaleBlindSquareTest(unittest.TestCase):
    """A last-known square the attacker can currently watch is provably
    empty: it must not be kept as a blind-attack guess (issue 28). Hidden
    or invisible creatures keep their (genuine) guesses."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.fighter, 'a', position=[2, 0])
        # Behind the wall column at x=4: unseen, but the remembered square
        # (3, 0) sits wide open in the fighter's line of sight.
        self.battle.add(self.goblin, 'b', position=[5, 0])
        self.battle.start(combat_order=[self.fighter, self.goblin])
        self.assertFalse(self.battle.can_see(self.fighter, self.goblin))
        # The remembered square is recorded at a fresh round (the map's own
        # name is the YAML title, so read it back rather than hard-code it).
        memory = self.battle.entity_state_for(self.fighter).setdefault(
            'unseen_memory', {})
        self.battle.round += 1
        memory[self.goblin.entity_uid] = {'pos': [3, 0],
                                          'round': self.battle.round,
                                          'map': self.map.name}

    def _sensed_squares(self):
        from natural20.utils.unseen_targets import sensed_creatures
        return [tuple(e['pos']) for e in sensed_creatures(self.battle, self.fighter)]

    def test_stale_guess_at_a_watchable_square_is_dropped(self):
        self.assertNotIn((3, 0), self._sensed_squares())

    def test_hidden_creature_keeps_its_guess(self):
        self.goblin.do_hide(30)
        # Re-seed after the hidden flip: a fresh sensed_creatures() call drops
        # markers for squares we can now watch, so the guess must be re-armed.
        memory = self.battle.entity_state_for(self.fighter).setdefault(
            'unseen_memory', {})
        memory[self.goblin.entity_uid] = {'pos': [3, 0],
                                          'round': self.battle.round,
                                          'map': self.map.name}
        self.assertIn((3, 0), self._sensed_squares())


class AreaSpellTargetingTest(unittest.TestCase):
    """Area spells, corpses and push bookkeeping (issues 11, 12, 13)."""

    def setUp(self):
        random.seed(2468)
        self.session = _session()
        self.map = Map(self.session, 'maps/empty_map')
        self.battle = Battle(self.session, self.map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.foe_a = PlayerCharacter.load(self.session, 'high_elf_fighter.yml', {'name': 'Foe A'})
        self.foe_b = PlayerCharacter.load(self.session, 'high_elf_fighter.yml', {'name': 'Foe B'})
        self.map.add(self.caster, 0, 0)
        self.map.add(self.foe_a, 1, 0)
        self.map.add(self.foe_b, 2, 0)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.foe_a, 'b', add_to_initiative=True)
        self.battle.add(self.foe_b, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.foe_a, self.foe_b])

    def _force_failed_saves(self, *creatures):
        class _FailRoll:
            def result(self):
                return 0

            def __lt__(self, other):
                return True

            def __ge__(self, other):
                return False

            def prob(self, _dc):
                return 1.0

        for creature in creatures:
            creature.save_throw = lambda *a, **k: _FailRoll()

    def test_thunderwave_push_destinations_are_committed_in_sequence(self):
        """Push landing squares are computed at commit time, so a creature
        blocked by another pushed creature still moves once that square is
        freed, and no two pushed creatures share a square."""
        from natural20.spell.thunderwave_spell import ThunderwaveSpell

        self._force_failed_saves(self.foe_a, self.foe_b)
        spell = ThunderwaveSpell(self.session, self.caster, 'thunderwave',
                                 self.session.load_spell('thunderwave'))
        action = SimpleNamespace(target=[3, 0], at_level=1, source=self.caster)
        items = spell.resolve(self.caster, self.battle, action, self.map)

        pushes = [item for item in items if item.get('type') == 'thunderwave_push']
        self.assertEqual(len(pushes), 2, "both foes should be pushed")
        for item in pushes:
            self.assertIn('push_from', item)
            self.assertIsNone(item.get('push_to'),
                              "landing squares must not be frozen at build time")

        # Commit the far foe's push first: that frees the square the near foe
        # was blocked by.
        far = next(item for item in pushes if item['target'] is self.foe_b)
        near = next(item for item in pushes if item['target'] is self.foe_a)
        ThunderwaveSpell.apply(self.battle, far, self.session)
        self.assertEqual(self.map.position_of(self.foe_b), [4, 0])
        ThunderwaveSpell.apply(self.battle, near, self.session)

        pos_a = self.map.position_of(self.foe_a)
        pos_b = self.map.position_of(self.foe_b)
        self.assertNotEqual(pos_a, pos_b, f"both foes ended on {pos_a}")
        self.assertNotEqual(pos_a, [1, 0], "the near foe never moved although the way opened up")

    def test_burning_hands_skips_corpses(self):
        from natural20.spell.burning_hands_spell import BurningHandsSpell

        self.foe_b.make_dead()
        spell = BurningHandsSpell(self.session, self.caster, 'burning_hands',
                                  self.session.load_spell('burning_hands'))
        action = SimpleNamespace(target=[4, 0], at_level=1, source=self.caster)
        items = spell.resolve(self.caster, self.battle, action, self.map)
        damaged = [item.get('target') for item in items if item.get('type') == 'spell_damage']
        self.assertIn(self.foe_a, damaged)
        self.assertNotIn(self.foe_b, damaged)

    def test_burning_hands_rolls_area_damage_once(self):
        """One casting, one damage roll shared by everyone in the cone."""
        from natural20.spell.burning_hands_spell import BurningHandsSpell

        third = PlayerCharacter.load(self.session, 'high_elf_fighter.yml', {'name': 'Foe C'})
        self.map.add(third, 2, 1)
        self.battle.add(third, 'b', add_to_initiative=True)
        self._force_failed_saves(self.foe_a, self.foe_b, third)

        spell = BurningHandsSpell(self.session, self.caster, 'burning_hands',
                                  self.session.load_spell('burning_hands'))
        action = SimpleNamespace(target=[4, 0], at_level=1, source=self.caster)
        items = spell.resolve(self.caster, self.battle, action, self.map)
        rolls = [item['damage_roll'] for item in items if item.get('type') == 'spell_damage']
        self.assertGreaterEqual(len(rolls), 2, "expected several creatures in the cone")
        first = rolls[0]
        self.assertTrue(all(roll is first for roll in rolls),
                        "area damage was rolled per creature")


class ShieldReactionGatingTest(unittest.TestCase):
    """Shield must not be offered when the +5 cannot change the outcome
    (issue 14: natural 20s hit anyway, natural 1s already missed)."""

    class AlwaysTake:
        def __init__(self):
            self.user = None

        def select_reaction(self, entity, battle, map, valid_actions, event):
            return valid_actions[0]

        def select_action(self, battle, entity, valid_actions):
            return valid_actions[0]

        def move_for(self, entity, battle):
            return None

    def setUp(self):
        random.seed(11)
        self.session = _session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.map.add(self.mage, 5, 5)
        self.battle.add(self.mage, 'a', add_to_initiative=True)
        self.skeleton = self.session.npc('skeleton')
        self.battle.add(self.skeleton, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.skeleton, self.mage])
        self.mage.reset_turn(self.battle)
        self.battle.set_controller_for(self.mage, self.AlwaysTake())
        self.ac = self.mage.armor_class()

    def _roll(self, face):
        # Natural `face` whose total lands exactly on the current AC, i.e.
        # squarely inside the +5 window where Shield would be offered.
        return DieRoll([face], self.ac - face)

    def _react(self, attack_roll):
        return ShieldSpell.after_attack_roll(
            self.battle, self.mage, self.skeleton, attack_roll, self.ac,
            opts={'original_action': None})

    def test_natural_20_does_not_offer_shield(self):
        slots = self.mage.spell_slots_count(1, 'wizard')
        items, _ = self._react(self._roll(20))
        self.assertEqual(items, [])
        self.assertEqual(self.mage.spell_slots_count(1, 'wizard'), slots)
        self.assertFalse(ShieldSpell.is_active_on(self.mage))

    def test_natural_1_does_not_offer_shield(self):
        slots = self.mage.spell_slots_count(1, 'wizard')
        items, _ = self._react(self._roll(1))
        self.assertEqual(items, [])
        self.assertEqual(self.mage.spell_slots_count(1, 'wizard'), slots)
        self.assertFalse(ShieldSpell.is_active_on(self.mage))

    def test_normal_roll_in_window_still_offers_shield(self):
        slots = self.mage.spell_slots_count(1, 'wizard')
        items, force_miss = self._react(self._roll(10))
        self.assertTrue(items, "Shield should still be offered mid-window")
        self.assertEqual(force_miss, 'force_miss')
        self.assertEqual(self.mage.spell_slots_count(1, 'wizard'), slots - 1)


class RayOfFrostTest(unittest.TestCase):
    """Two Rays of Frost must not share one slow, and their start-of-turn
    hooks must not pile up on the caster (issue 15)."""

    def setUp(self):
        random.seed(31)
        self.session = _session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.foe = PlayerCharacter.load(self.session, 'high_elf_fighter.yml',
                                        {'name': 'Frozen Foe'})
        self.map.add(self.mage, 0, 5)
        self.map.add(self.foe, 1, 5)
        self.battle.add(self.mage, 'a', add_to_initiative=True)
        self.battle.add(self.foe, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.mage, self.foe])
        self.mage.reset_turn(self.battle)

    def _cast(self):
        spell = RayOfFrostSpell(self.session, self.mage, 'ray_of_frost',
                                self.session.load_spell('ray_of_frost'))
        action = SimpleNamespace(target=self.foe, at_level=None)
        spell.action = action
        DieRoll.fudge(20)  # guarantee the attack roll hits
        try:
            items = spell.resolve(self.mage, self.battle, action, self.map)
        finally:
            DieRoll.unfudge()
        for item in items:
            RayOfFrostSpell.apply(self.battle, item, self.session)
        return spell

    def _hooks(self):
        return [h for h in self.mage.entity_event_hooks.get('start_of_turn', [])
                if h.get('handler') is RayOfFrostSpell]

    def test_slow_does_not_stack_and_replaces_the_earlier_cast(self):
        first = self._cast()
        second = self._cast()

        slows = [e for e in self.foe.effects.get('speed_override', [])
                 if e.get('handler') is RayOfFrostSpell]
        self.assertEqual(len(slows), 1, "the two slows stacked")
        self.assertIs(slows[0]['effect'], second)

        # The replaced cast is gone from the target AND from the caster's
        # bookkeeping: casted_effects and start-of-turn hooks.
        self.assertEqual(len(self._hooks()), 1, "start-of-turn hooks piled up")
        self.assertIs(self._hooks()[0]['effect'], second)
        casted = [e.get('effect') for e in self.mage.casted_effects]
        self.assertNotIn(first, casted)
        self.assertIn(second, casted)

    def test_expiry_cleans_up_target_and_caster(self):
        spell = self._cast()
        RayOfFrostSpell.start_of_turn(self.mage, {'effect': spell})
        self.assertEqual([e for e in self.foe.effects.get('speed_override', [])
                          if e.get('handler') is RayOfFrostSpell], [])
        self.assertEqual(self._hooks(), [])
        self.assertNotIn(spell, [e.get('effect') for e in self.mage.casted_effects])


class MagicMissileEstimateTest(unittest.TestCase):
    """The heuristic AI scored Magic Missile at 0 damage and never cast it
    (issue 18)."""

    def setUp(self):
        self.session = _session()
        self.mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')

    def test_expected_damage_is_positive_and_analytic(self):
        spell = MagicMissileSpell(self.session, self.mage, 'magic_missile',
                                  self.session.load_spell('magic_missile'))
        spell.action = SimpleNamespace(at_level=1, target=None)
        before = random.getstate()
        self.assertEqual(spell.avg_damage(None), 3 * 3.5)
        spell.action = SimpleNamespace(at_level=2, target=None)
        self.assertEqual(spell.avg_damage(None), 4 * 3.5)
        self.assertEqual(spell.compute_hit_probability(None), 1.0)
        self.assertEqual(random.getstate(), before)


class AreaPlacementScoringTest(unittest.TestCase):
    """Sphere placement (Shatter, Acid Splash) must respect line of effect
    from the burst center and only trust sensed squares by their confidence
    (issue 19)."""

    class FakeMap:
        def __init__(self, entities, blocked):
            self.entities = entities
            self.blocked = blocked

        def line_of_sight(self, cx, cy, sx, sy):
            return None if (sx, sy) in self.blocked else True

        def entity_at(self, x, y):
            return self.entities.get((x, y))

    def _foe(self, conscious=True):
        class Foe:
            def dead(self):
                return not conscious

            def conscious(self):
                return conscious
        return Foe()

    def test_creature_in_total_cover_from_the_center_never_counts(self):
        foe = self._foe()
        map_ = self.FakeMap({(2, 0): foe}, blocked={(2, 0)})
        value = _score_squares([(2, 0)], None, None, map_,
                           aware=({foe}, {}, set()), center=(0, 0))
        self.assertEqual(value, 0)

    def test_visible_foe_in_line_of_effect_scores(self):
        foe = self._foe()
        map_ = self.FakeMap({(2, 0): foe}, blocked=set())
        value = _score_squares([(2, 0)], None, None, map_,
                           aware=({foe}, {}, set()), center=(0, 0))
        self.assertEqual(value, 1)

    def test_downed_and_corpse_squares_score_less_than_zero_nothing(self):
        class Corpse:
            def dead(self):
                return True
        map_ = self.FakeMap({(2, 0): Corpse()}, blocked=set())
        value = _score_squares([(2, 0)], None, None, map_,
                           aware=({(Corpse(),)}, {}, set()), center=(0, 0))
        # No living foe: empty and corpse squares contribute nothing.
        self.assertEqual(value, 0)

    def test_stale_last_known_square_counts_only_its_confidence(self):
        map_ = self.FakeMap({}, blocked=set())
        value = _score_squares([(2, 0)], None, None, map_,
                           aware=(set(), {(2, 0): 0.2}, set()), center=(0, 0))
        self.assertAlmostEqual(value, 0.2)


class MageArmorAcTest(unittest.TestCase):
    """Mage Armor must never lower a better AC (issue 26)."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.map.add(self.fighter, 0, 0)
        self.battle.add(self.fighter, 'a', add_to_initiative=True)
        self.battle.start(combat_order=[self.fighter])
        self.fighter.reset_turn(self.battle)

    def _apply(self, entity):
        spell = MageArmorSpell(self.session, entity, 'mage_armor',
                               self.session.load_spell('mage_armor'))
        MageArmorSpell.apply(self.battle, {
            'type': 'mage_armor', 'source': entity, 'target': entity, 'effect': spell,
        }, self.session)
        return spell

    def test_does_not_lower_a_higher_base_ac(self):
        base = self.fighter.armor_class()
        self._apply(self.fighter)
        self.assertEqual(self.fighter.armor_class(), max(base, 13 + self.fighter.dex_mod()))
        self.assertGreaterEqual(self.fighter.armor_class(), base)

    def test_raises_a_lower_unarmored_ac(self):
        mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.map.add(mage, 1, 0)
        self.battle.add(mage, 'a', add_to_initiative=True)
        mage.reset_turn(self.battle)
        base = mage.armor_class()
        self.assertGreater(base, 0)
        self._apply(mage)
        self.assertEqual(mage.armor_class(), max(base, 13 + mage.dex_mod()))


class AutoCritAgainstHelplessTest(unittest.TestCase):
    """Any attack within 5 feet of a paralyzed or unconscious creature is a
    critical hit when it hits, including ranged and spell attacks
    (issue 27)."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'maps/empty_map')
        self.battle = Battle(self.session, self.map)
        self.attacker = PlayerCharacter.load(self.session, 'high_elf_fighter.yml',
                                             {'name': 'Attacker'})
        self.foe = PlayerCharacter.load(self.session, 'high_elf_fighter.yml',
                                        {'name': 'Helpless Foe'})
        self.map.add(self.attacker, 0, 0)
        self.map.add(self.foe, 1, 0)
        self.battle.add(self.attacker, 'a', add_to_initiative=True)
        self.battle.add(self.foe, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.attacker, self.foe])
        self.attacker.reset_turn(self.battle)

    def _drop(self):
        self.foe.attributes['hp'] = 0
        self.foe.make_unconscious()

    def test_spell_attack_crits_within_five_feet(self):
        self._drop()
        roll = DieRoll([10], 5)  # plain hit, not a natural 20
        self.assertTrue(spell_attack_is_critical(roll, self.attacker, self.foe, self.battle))

    def test_spell_attack_out_of_reach_is_not_auto_crit(self):
        self.map.move_to(self.foe, 4, 0, self.battle)  # 15+ feet away
        self._drop()
        roll = DieRoll([10], 5)
        self.assertFalse(spell_attack_is_critical(roll, self.attacker, self.foe, self.battle))

    def test_conscious_target_is_not_auto_crit(self):
        roll = DieRoll([10], 5)
        self.assertFalse(spell_attack_is_critical(roll, self.attacker, self.foe, self.battle))

    def test_ranged_weapon_attack_crits_adjacent_helpless_target(self):
        self._drop()
        ac = self.foe.armor_class()
        goblin = self.session.npc('goblin')
        self.map.add(goblin, 0, 1)
        self.battle.add(goblin, 'a', add_to_initiative=True)
        action = AttackAction(self.session, goblin, 'attack')
        action.target = self.foe
        action.npc_action = {
            'name': 'Shortbow', 'type': 'ranged_attack', 'range': 20, 'targets': 1,
            'attack': 4, 'damage': 2, 'damage_die': '1d6+2', 'damage_type': 'piercing',
        }
        DieRoll.fudge(ac - 4)  # hits exactly, no natural 20
        try:
            self.battle.execute_action(action)
        finally:
            DieRoll.unfudge()
        damage_items = [i for i in action.result if i.get('type') == 'damage']
        self.assertTrue(damage_items, "the attack should have hit")
        self.assertTrue(all(i.get('critical') for i in damage_items),
                        "ranged attack on an adjacent unconscious foe must crit")

    def test_conscious_target_ranged_attack_is_not_critical(self):
        ac = self.foe.armor_class()
        goblin = self.session.npc('goblin')
        self.map.add(goblin, 0, 1)
        self.battle.add(goblin, 'a', add_to_initiative=True)
        action = AttackAction(self.session, goblin, 'attack')
        action.target = self.foe
        action.npc_action = {
            'name': 'Shortbow', 'type': 'ranged_attack', 'range': 20, 'targets': 1,
            'attack': 4, 'damage': 2, 'damage_die': '1d6+2', 'damage_type': 'piercing',
        }
        DieRoll.fudge(ac - 4)
        try:
            self.battle.execute_action(action)
        finally:
            DieRoll.unfudge()
        damage_items = [i for i in action.result if i.get('type') == 'damage']
        self.assertTrue(damage_items)
        self.assertFalse(any(i.get('critical') for i in damage_items))


class HidePlainSightTest(unittest.TestCase):
    """2014: you can't hide from a creature that can see you clearly
    (issue 29). Stealth no longer beats a low passive Perception while in
    plain sight."""

    def setUp(self):
        random.seed(5)
        self.session = _session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.rogue = PlayerCharacter.load(self.session, 'elf_rogue.yml')
        self.foe = self.session.npc('skeleton')
        self.battle.add(self.rogue, 'a', position=[0, 0])
        self.battle.add(self.foe, 'b', position=[3, 0])
        self.battle.start(combat_order=[self.rogue, self.foe])
        self.rogue.reset_turn(self.battle)

    def _hide(self):
        hide = HideAction(self.session, self.rogue, 'hide')
        DieRoll.fudge(20)  # best possible stealth roll
        try:
            hide.resolve(self.session, self.map, opts={'battle': self.battle})
        finally:
            DieRoll.unfudge()
        return hide

    def test_hiding_in_plain_sight_fails_even_against_blind_dumb_foes(self):
        # The pre-fix rule only failed when the foe's passive Perception beat
        # the stealth roll: a skeleton (Passive Perception 9) lost this contest.
        self.foe.properties['passive_perception'] = 1
        result = self._hide().result[0]
        self.assertEqual(result['result'], 'failed')
        self.assertTrue(any('can see' in reason for reason in result['reason']),
                        f"unexpected reasons: {result['reason']}")
        self.assertNotIn('hidden', self.rogue.statuses)

    def test_hiding_with_no_conscious_witness_succeeds(self):
        self.foe.attributes['hp'] = 0
        self.foe.make_unconscious()
        result = self._hide().result[0]
        self.assertEqual(result['result'], 'success')

    def test_2024_requires_cover_or_obscuration_and_dc_15(self):
        campaign = _campaign_copy('5e-2024')
        try:
            session = Session(str(campaign))
            map_ = Map(session, 'battle_sim')
            battle = Battle(session, map_)
            rogue = PlayerCharacter.load(session, 'elf_rogue.yml')
            foe = session.npc('skeleton')
            battle.add(rogue, 'a', position=[0, 0])
            battle.add(foe, 'b', position=[3, 0])
            battle.start(combat_order=[rogue, foe])
            rogue.reset_turn(battle)
            hide = HideAction(session, rogue, 'hide')
            DieRoll.fudge(20)
            try:
                hide.resolve(session, map_, opts={'battle': battle})
            finally:
                DieRoll.unfudge()
            result = hide.result[0]
            self.assertEqual(result['result'], 'failed')
        finally:
            _drop_campaign_copy(campaign)


def _campaign_copy(ruleset):
    """Copy of tests/fixtures with game.yml switched to `ruleset`."""
    tmp = tempfile.mkdtemp(prefix='n20-fixtures-')
    dest = Path(tmp) / 'campaign'
    shutil.copytree(Path(__file__).parent / 'fixtures', dest,
                    ignore=shutil.ignore_patterns('tmp', '__pycache__', '*.pyc'))
    game_path = dest / 'game.yml'
    with game_path.open('r', encoding='utf-8') as fh:
        game = yaml.safe_load(fh) or {}
    game['ruleset'] = ruleset
    with game_path.open('w', encoding='utf-8') as fh:
        yaml.safe_dump(game, fh)
    return dest


def _drop_campaign_copy(dest):
    """Delete a campaign copy without poisoning the global i18n load path."""
    import i18n
    locales = str((dest / 'locales').resolve())
    i18n.load_path[:] = [p for p in i18n.load_path if str(p) != locales]
    shutil.rmtree(dest.parent, ignore_errors=True)


class Ruleset2024DataTest(unittest.TestCase):
    """2024 ruleset data fixes: wizard subclass level (issue 21) and the
    Soldier origin feat (issue 23)."""

    @classmethod
    def setUpClass(cls):
        cls.campaign = _campaign_copy('5e-2024')
        # The fixture campaign carries its own 2014 class sheets; drop the
        # wizard so the 5e-2024 ruleset overlay applies (same as real 2024
        # campaigns that do not redefine the class locally).
        (cls.campaign / 'char_classes' / 'wizard.yml').unlink()
        cls.session = Session(str(cls.campaign))

    @classmethod
    def tearDownClass(cls):
        _drop_campaign_copy(cls.campaign)

    def test_wizard_gets_arcane_tradition_at_level_3(self):
        wizard = self.session.load_classes().get('wizard') or {}
        progression = wizard.get('progression') or {}
        level_2 = (progression.get('level_2') or {}).get('class_features') or []
        level_3 = (progression.get('level_3') or {}).get('class_features') or []
        self.assertNotIn('arcane_tradition', level_2)
        self.assertIn('arcane_tradition', level_3)

    def test_evoker_uses_the_2024_feature_schedule(self):
        wizard = self.session.load_classes().get('wizard') or {}
        evoker = (wizard.get('arcane_tradition_features') or {}).get('school_of_evocation') or {}
        self.assertFalse(evoker.get('level_2'))
        level_3 = evoker.get('level_3') or []
        self.assertIn('evocation_savant', level_3)
        self.assertIn('potent_cantrip', level_3)
        self.assertIn('sculpt_spells', evoker.get('level_6') or [])
        self.assertIn('empowered_evocation', evoker.get('level_10') or [])
        self.assertIn('overchannel', evoker.get('level_14') or [])

    def test_soldier_origin_feat_is_savage_attacker(self):
        soldier = (self.session.load_backgrounds() or {}).get('soldier') or {}
        self.assertEqual(soldier.get('origin_feat'), 'savage_attacker')


class ThrownRangeDataTest(unittest.TestCase):
    """SRD 5.1/5.2.1: dagger and handaxe are Thrown (range 20/60),
    not 30/120 and 30/60 (issue 25)."""

    def test_thrown_ranges(self):
        session = _session()
        for kind in ('dagger', 'handaxe'):
            weapon = session.load_weapon(kind)
            self.assertEqual(weapon.get('thrown'), {'range': 20, 'range_max': 60},
                             f"{kind} thrown range wrong: {weapon.get('thrown')}")


class SavageAttackerTest(unittest.TestCase):
    """The 2024 Soldier origin feat: roll a weapon's damage dice twice,
    keep either total, once per turn (issue 23)."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'maps/empty_map')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.map.add(self.fighter, 0, 0)
        self.battle.add(self.fighter, 'a', add_to_initiative=True)
        self.battle.start(combat_order=[self.fighter])
        self.fighter.reset_turn(self.battle)
        self.longsword = self.session.load_weapon('longsword')

    def test_feat_grants_roll_twice_once_per_turn(self):
        from natural20.utils.feat_mechanics import should_roll_damage_twice

        self.fighter.properties['feats'] = ['savage_attacker']
        self.assertTrue(should_roll_damage_twice(self.fighter, self.longsword, self.battle))
        self.assertFalse(should_roll_damage_twice(self.fighter, self.longsword, self.battle))
        self.fighter.reset_turn(self.battle)
        self.assertTrue(should_roll_damage_twice(self.fighter, self.longsword, self.battle))

    def test_without_the_feat_nothing_applies(self):
        from natural20.utils.feat_mechanics import should_roll_damage_twice

        self.assertFalse(should_roll_damage_twice(self.fighter, self.longsword, self.battle))

    def test_soldier_feat_yaml_exists(self):
        from natural20.yaml_loader import load_campaign_resource_path
        loaded = load_campaign_resource_path(self.session.root_path, 'feats/savage_attacker.yml')
        definition = loaded.get('savage_attacker', loaded)
        self.assertIsInstance(definition, dict)
        rules = definition.get('damage_roll_rules') or []
        self.assertTrue(any(rule.get('roll_twice_best') for rule in rules))


class SpellScoringSweepTest(unittest.TestCase):
    """Issue 17: hit-chance / mean-damage scoring for EVERY implemented spell
    must not draw from the game RNG (an estimate that rolls shifts every
    later die in the fight and is noisy)."""

    def test_scoring_the_whole_catalog_draws_no_dice(self):
        from natural20.utils.spell_loader import (load_spell_class,
                                                  resolve_spell_class_key)

        session = _session()
        map_ = Map(session, 'battle_sim')
        battle = Battle(session, map_)
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        foe = PlayerCharacter.load(session, 'high_elf_fighter.yml',
                                   {'name': 'Scoring Dummy'})
        map_.add(mage, 0, 5)
        map_.add(foe, 2, 5)
        battle.add(mage, 'a', add_to_initiative=True)
        battle.add(foe, 'b', add_to_initiative=True)
        battle.start(combat_order=[mage, foe])

        scored = 0
        for slug, meta in sorted(session.load_all_spells().items()):
            try:
                spell_class = load_spell_class(resolve_spell_class_key(slug, meta))
            except Exception:
                continue
            if spell_class.__module__ == 'natural20.spell.wizard_spells':
                continue
            spell = spell_class(session, mage, slug, dict(meta))
            spell.action = SimpleNamespace(target=foe,
                                           at_level=max(1, meta.get('level') or 1),
                                           source=mage)
            before = random.getstate()
            try:
                spell.compute_hit_probability(battle)
            except Exception:
                pass
            try:
                spell.avg_damage(battle)
            except Exception:
                pass
            self.assertEqual(before, random.getstate(),
                             f"scoring {slug} consumed game RNG")
            scored += 1
        self.assertGreater(scored, 50,
                           "expected to exercise most of the spell catalog")


# ---------------------------------------------------------------------------
# Second batch (issues 31-44), reported by the Forests and Faeries team.
# ---------------------------------------------------------------------------


class WeaponMasteryMarkerTest(unittest.TestCase):
    """Issue 31/32: Sap/Vex markers were spent by AI scoring passes, and
    Sap/Slow never expired when their applier was dead or incapacitated."""

    def _setup(self):
        session = _session()
        map_ = Map(session, 'battle_sim_objects')
        battle = Battle(session, map_)
        attacker = PlayerCharacter.load(session, 'high_elf_fighter.yml',
                                        {'name': 'Vex Owner'})
        victim = PlayerCharacter.load(session, 'high_elf_mage.yml',
                                      {'name': 'Sapped Victim'})
        battle.add(attacker, 'a', position=[0, 5])
        battle.add(victim, 'b', position=[2, 5])
        return session, battle, attacker, victim

    def test_scoring_peeks_sap_without_spending_it(self):
        from natural20.weapons import compute_advantages_and_disadvantages
        session, battle, attacker, victim = self._setup()
        weapon = session.load_weapon('longsword')
        attacker._sap_next_attack = True

        for _ in range(3):
            _, disadvantages = compute_advantages_and_disadvantages(
                session, attacker, victim, weapon, battle=battle,
                consume_masteries=False)
            self.assertIn('weapon_mastery_sap', disadvantages)
            self.assertTrue(attacker._sap_next_attack,
                            "hit-chance scoring spent the Sap marker")

        _, disadvantages = compute_advantages_and_disadvantages(
            session, attacker, victim, weapon, battle=battle)
        self.assertIn('weapon_mastery_sap', disadvantages)
        self.assertFalse(attacker._sap_next_attack,
                         "the real attack roll must spend the marker")

    def test_scoring_peeks_vex_without_spending_it(self):
        from natural20.weapons import compute_advantages_and_disadvantages
        session, battle, attacker, victim = self._setup()
        weapon = session.load_weapon('longsword')
        attacker._vex_advantage_vs = {victim.entity_uid: True}

        advantages, _ = compute_advantages_and_disadvantages(
            session, attacker, victim, weapon, battle=battle,
            consume_masteries=False)
        self.assertIn('weapon_mastery_vex', advantages)
        self.assertTrue(attacker._vex_advantage_vs.get(victim.entity_uid))

        attack = AttackAction(session, attacker, 'attack', {'target': victim})
        attack.using = 'longsword'
        attack.target = victim
        _, _, _ = attack.compute_advantage_info(battle)
        self.assertTrue(attacker._vex_advantage_vs.get(victim.entity_uid),
                        "AttackAction.compute_hit_probability spent the Vex marker")

    def test_sap_expires_at_start_of_applier_turn_when_incapacitated(self):
        session, battle, attacker, victim = self._setup()
        victim._sap_next_attack = True
        victim._sap_from = attacker.entity_uid
        battle.start(combat_order=[attacker, victim])
        attacker.add_condition('incapacitated') if hasattr(attacker, 'add_condition') \
            else attacker.statuses.append('incapacitated')
        battle.start_turn()
        self.assertFalse(victim._sap_next_attack,
                         "Sap must expire at the start of the applier's turn "
                         "even when the applier never acts")

    def test_sap_expires_when_dead_appliers_turn_is_skipped(self):
        session, battle, attacker, victim = self._setup()
        victim._sap_next_attack = True
        victim._sap_from = attacker.entity_uid
        battle.start(combat_order=[attacker, victim])
        attacker.make_dead(cause='test')
        battle.skip_dead_turns()
        self.assertFalse(victim._sap_next_attack,
                         "a dead creature's next turn never starts, so its "
                         "Sap/Slow markers must expire when skipped")


class FearApproachTest(unittest.TestCase):
    """Issue 33: frightened creatures must not be able to move closer to the
    source of their fear (voluntary movement only)."""

    def setUp(self):
        from natural20.utils.fear import apply_fear
        self.session = _session()
        self.map = Map(self.session, 'large_map')
        self.battle = Battle(self.session, self.map)
        self.source = PlayerCharacter.load(self.session, 'high_elf_fighter.yml',
                                           {'name': 'Fearsome'})
        self.target = PlayerCharacter.load(self.session, 'high_elf_mage.yml',
                                           {'name': 'Scaredy'})
        self.battle.add(self.source, 'a', position=[3, 0])
        self.battle.add(self.target, 'b', position=[0, 0])
        apply_fear(self.target, self.source)

    def test_path_toward_fear_source_truncated(self):
        from natural20.utils.fear import truncate_path_for_fear
        kept = truncate_path_for_fear(self.target,
                                      [(0, 0), (1, 0), (2, 0)],
                                      self.map, self.battle)
        self.assertEqual(kept, [(0, 0)])

    def test_sideways_steps_stay_legal(self):
        from natural20.utils.fear import truncate_path_for_fear
        kept = truncate_path_for_fear(self.target,
                                      [(0, 0), (0, 1), (1, 1)],
                                      self.map, self.battle)
        self.assertEqual(kept, [(0, 0), (0, 1)])

    def test_move_action_path_is_clipped(self):
        from natural20.actions.move_action import MoveAction
        action = MoveAction(self.session, self.target, 'move')
        action.move_path = [(0, 0), (1, 0)]
        self.battle.entity_state_for(self.target)['movement'] = 30
        action.resolve(self.session, self.map,
                       {'battle': self.battle, 'ignore_opportunity_attacks': True})
        for item in action.result:
            MoveAction.apply(self.battle, item, self.session)
        self.assertEqual(list(self.map.position_of(self.target)), [0, 0])

        # Control: the same step is legal for a creature that isn't afraid.
        brave = PlayerCharacter.load(self.session, 'high_elf_mage.yml',
                                     {'name': 'Brave'})
        self.battle.add(brave, 'c', position=[0, 1])
        control = MoveAction(self.session, brave, 'move')
        control.move_path = [(0, 1), (1, 0)]
        self.battle.entity_state_for(brave)['movement'] = 30
        control.resolve(self.session, self.map,
                        {'battle': self.battle, 'ignore_opportunity_attacks': True})
        for item in control.result:
            MoveAction.apply(self.battle, item, self.session)
        self.assertEqual(list(self.map.position_of(brave)), [1, 0])

    def test_unfrightened_creature_unaffected(self):
        from natural20.utils.fear import truncate_path_for_fear
        other = PlayerCharacter.load(self.session, 'high_elf_fighter.yml',
                                     {'name': 'Brave'})
        self.battle.add(other, 'c', position=[0, 1])
        kept = truncate_path_for_fear(other, [(0, 1), (1, 0)], self.map, self.battle)
        self.assertEqual(kept, [(0, 1), (1, 0)])


class ProtectionFromEvilAndGoodTest(unittest.TestCase):
    """Issue 34: the spell's benefits were never actually applied."""

    def setUp(self):
        from natural20.spell.protection_from_evil_and_good_spell import (
            ProtectionEvilAndGoodEffect,
        )
        self.session = _session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.warded = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(self.warded, 'a', position=[0, 5])
        self.skeleton = self.session.npc('skeleton')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.skeleton, 'b', position=[5, 5])
        self.battle.add(self.goblin, 'b', position=[6, 5])

        effect = ProtectionEvilAndGoodEffect(self.warded, {})
        for key in ('targeted_advantage_override', 'condition_immunity'):
            self.warded.register_effect(key, ProtectionEvilAndGoodEffect,
                                        effect=effect, source=self.warded)

    def test_cannot_be_frightened_by_undead_but_humans_still_can(self):
        from natural20.utils.fear import apply_fear
        self.assertTrue(self.warded.immune_to_condition('frightened',
                                                        source=self.skeleton))
        self.assertFalse(self.warded.immune_to_condition('frightened',
                                                         source=self.goblin))
        self.assertFalse(apply_fear(self.warded, self.skeleton))
        self.assertTrue(apply_fear(self.warded, self.goblin))

    def test_protected_types_attack_at_disadvantage(self):
        from natural20.weapons import compute_advantages_and_disadvantages
        weapon = self.session.load_weapon('club')
        _, disadvantages = compute_advantages_and_disadvantages(
            self.session, self.skeleton, self.warded, weapon, battle=self.battle)
        self.assertIn('protection_from_evil_and_good', disadvantages)

        _, disadvantages = compute_advantages_and_disadvantages(
            self.session, self.goblin, self.warded, weapon, battle=self.battle)
        self.assertNotIn('protection_from_evil_and_good', disadvantages)


class _NoHealHandler:
    @staticmethod
    def heal_override(entity, opts=None):
        return 0


class _Nat20Roll:
    def nat_20(self):
        return True

    def nat_1(self):
        return False

    def result(self):
        return 20


class NoHealingAndDeathSavesTest(unittest.TestCase):
    """Issue 35: creatures that can't regain hit points (swarms, Chill
    Touch) must not pop up on a natural 20 death save."""

    def test_can_gain_hit_points_gates(self):
        session = _session()
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        self.assertTrue(fighter.can_gain_hit_points(1))

        fighter.register_effect('heal_override', _NoHealHandler,
                                effect='chill_touch', source=None)
        self.assertFalse(fighter.can_gain_hit_points(1))

        fighter.dismiss_effect('heal_override') if hasattr(fighter, 'dismiss_effect') else None
        fighter.effects.pop('heal_override', None)
        fighter.class_feature = lambda name: name == 'swarm'
        self.assertFalse(fighter.can_gain_hit_points(1))

    def test_nat20_death_save_without_healing_stays_down(self):
        from unittest import mock
        session = _session()
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        fighter.attributes['hp'] = 0
        fighter.make_unconscious()
        fighter.register_effect('heal_override', _NoHealHandler,
                                effect='chill_touch', source=None)
        with mock.patch('natural20.die_roll.DieRoll.roll_with_lucky',
                        classmethod(lambda cls, *a, **k: _Nat20Roll())):
            fighter.death_saving_throw()
        self.assertEqual(fighter.hp(), 0)
        self.assertEqual(fighter.death_saves, 1)
        self.assertFalse(fighter.conscious())

    def test_nat20_death_save_usually_restores_one(self):
        from unittest import mock
        session = _session()
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        fighter.attributes['hp'] = 0
        fighter.make_unconscious()
        with mock.patch('natural20.die_roll.DieRoll.roll_with_lucky',
                        classmethod(lambda cls, *a, **k: _Nat20Roll())):
            fighter.death_saving_throw()
        self.assertEqual(fighter.hp(), 1)
        self.assertTrue(fighter.conscious())


class ReactionStartOfBattleTest(unittest.TestCase):
    """Issue 36: combatants start with a reaction available (opportunity
    attacks happen before your first turn)."""

    def test_reaction_available_before_first_turn(self):
        session = _session()
        map_ = Map(session, 'battle_sim_objects')
        battle = Battle(session, map_)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=[0, 5])
        state = battle.entity_state_for(fighter)
        self.assertEqual(state.get('reaction'), 1)


class HiddenSensesTest(unittest.TestCase):
    """Issue 37: failing to notice a hidden creature must not disable the
    observer's other senses (blindsight range, truesight)."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'large_map')
        self.attacker = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.sneaky = PlayerCharacter.load(self.session, 'halfling_rogue.yml')
        self.map.add(self.attacker, 0, 0)
        self.map.add(self.sneaky, 2, 0)

    def test_hidden_undetected_then_truesight_sees_it(self):
        self.sneaky.do_hide(30)
        self.assertFalse(self.attacker.passive_perception() >= 30)
        self.assertFalse(self.map.can_see(self.attacker, self.sneaky),
                         "passive Perception should miss DC 30 stealth")
        self.attacker.properties['truesight'] = 60
        try:
            self.assertTrue(self.map.can_see(self.attacker, self.sneaky),
                            "truesight sees hidden creatures in range")
        finally:
            self.attacker.properties.pop('truesight', None)

    def test_blindsight_locates_hidden_creature(self):
        self.sneaky.do_hide(30)
        self.assertFalse(self.map.can_see(self.attacker, self.sneaky))
        self.attacker.has_blindsight = lambda: True
        self.attacker.blindsight = lambda feet: feet <= 30
        self.assertTrue(self.map.can_see(self.attacker, self.sneaky),
                        "blindsight locates creatures regardless of hiding")


class PackTacticsGeometryTest(unittest.TestCase):
    """Issue 38: the flanking ally must be within 5 feet of the *target*,
    not within the ally's melee reach measured from the attacker."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.attacker = PlayerCharacter.load(self.session, 'high_elf_fighter.yml',
                                             {'name': 'Attacker'})
        self.target = self.session.npc('goblin')
        self.ally = self.session.npc('goblin')
        self.battle.add(self.attacker, 'a', position=[0, 5])
        self.battle.add(self.target, 'b', position=[2, 5])
        self.battle.add(self.ally, 'a', position=[1, 6])

    def test_ally_within_five_feet_of_target_counts(self):
        self.assertTrue(self.battle.ally_within_enemy_melee_range(
            self.attacker, self.target))

    def test_ally_ten_feet_from_target_does_not_count(self):
        self.map.remove(self.ally)
        self.map.add(self.ally, 0, 6)  # adjacent to attacker, 10 ft from target
        self.assertFalse(self.battle.ally_within_enemy_melee_range(
            self.attacker, self.target))

    def test_dead_ally_does_not_count(self):
        self.ally.make_dead(cause='test')
        self.assertFalse(self.battle.ally_within_enemy_melee_range(
            self.attacker, self.target))


class RageRulesTest(unittest.TestCase):
    """Issue 39: heavy armor voids rage benefits; rage ends early when a
    turn ends with no attack and no damage; Reckless Attack is a
    first-attack-only declaration."""

    def _barbarians(self):
        session = _session()
        map_ = Map(session, 'battle_sim_objects')
        battle = Battle(session, map_)
        raging = PlayerCharacter.load(session, 'goliath_barbarian.yml',
                                      {'name': 'Bare'})
        armored = PlayerCharacter.load(session, 'goliath_barbarian.yml',
                                       {'name': 'Plated'})
        foe = PlayerCharacter.load(session, 'high_elf_fighter.yml',
                                   {'name': 'Foe'})
        battle.add(raging, 'a', position=[0, 5])
        battle.add(armored, 'a', position=[0, 6])
        battle.add(foe, 'b', position=[2, 5])
        armored.equip('chain_mail', ignore_inventory=True)
        return session, battle, map_, raging, armored, foe

    def test_heavy_armor_blocks_rage_and_its_benefits(self):
        from natural20.actions.rage_action import RageAction
        from natural20.weapons import damage_modifier
        session, battle, _, raging, armored, _ = self._barbarians()
        self.assertTrue(armored.wearing_heavy_armor())
        self.assertFalse(RageAction.can(armored, battle))

        # Force the state to compare benefit application, not activation.
        armored.raging = True
        raging.raging = True
        self.assertIn('slashing', raging.effective_resistances())
        self.assertNotIn('slashing', armored.effective_resistances())

        weapon = session.load_weapon('longsword')
        self.assertNotEqual(damage_modifier(armored, weapon),
                            damage_modifier(raging, weapon),
                            "heavy armor must not also give the rage damage die")

    def test_rage_ends_early_when_turn_ends_without_attack_or_damage(self):
        session, battle, _, raging, _, foe = self._barbarians()
        raging.raging = True
        raging.rage_rounds_remaining = 10
        raging.reset_turn(battle)
        raging.resolve_trigger('end_of_turn', {'battle': battle})
        self.assertFalse(raging.is_raging())

    def test_damage_or_attack_keeps_rage_alive(self):
        session, battle, map_, raging, _, foe = self._barbarians()
        raging.raging = True
        raging.rage_rounds_remaining = 10
        raging.reset_turn(battle)
        raging.take_damage(2, battle=battle, damage_type='piercing')
        raging.resolve_trigger('end_of_turn', {'battle': battle})
        self.assertTrue(raging.is_raging(),
                        "taking damage since the last turn keeps the rage up")

        raging.reset_turn(battle)
        raging.resolve_trigger('attack_resolved', {'target': foe})
        raging.resolve_trigger('end_of_turn', {'battle': battle})
        self.assertTrue(raging.is_raging(),
                        "attacking a hostile creature keeps the rage up")

    def test_unconscious_ends_rage(self):
        session, battle, map_, raging, _, foe = self._barbarians()
        raging.raging = True
        raging.make_unconscious()
        self.assertFalse(raging.is_raging())

    def test_reckless_attack_gone_after_first_attack(self):
        from natural20.actions.rage_action import RecklessAttackAction
        session, battle, _, raging, _, foe = self._barbarians()
        raging.raging = True
        raging.reset_turn(battle)
        state = battle.entity_state_for(raging)
        state['action'] = 1
        self.assertTrue(RecklessAttackAction.can(raging, battle))
        state['attacks_this_turn'] = 1
        self.assertFalse(RecklessAttackAction.can(raging, battle),
                         "Reckless Attack is declared on your first attack "
                         "of the turn, not after Action Surge")


class SpellSlotTableTest(unittest.TestCase):
    """Issue 40: Cleric/Paladin slot lookups read the cantrip/placeholder
    column."""

    def test_cleric_slots_use_the_right_column(self):
        session = _session()
        cleric = PlayerCharacter.load(session, 'dwarf_cleric.yml')  # level 3
        self.assertEqual(cleric.max_slots_for_cleric(1), 4)
        self.assertEqual(cleric.max_slots_for_cleric(2), 2)
        self.assertEqual(cleric.max_slots_for_cleric(3), 0)

    def test_paladin_slots_use_the_right_column(self):
        session = _session()
        paladin = PlayerCharacter.load(session, 'goliath_paladin.yml')  # level 2
        self.assertEqual(paladin.max_slots_for_paladin(1), 2)
        self.assertEqual(paladin.max_slots_for_paladin(2), 0)


class NpcAcOverrideTest(unittest.TestCase):
    """Issue 41: NPC armor_class ignored Mage Armor-style ac_override."""

    def test_skeleton_with_mage_armor(self):
        session = _session()
        skeleton = session.npc('skeleton')
        self.assertEqual(skeleton.armor_class(), 13)
        skeleton.register_effect('ac_override', MageArmorSpell,
                                 effect='mage_armor', source=None)
        # 13 + DEX 2 beats the skeleton's natural 13.
        self.assertEqual(skeleton.armor_class(), 15)


class MissingSrdWeaponsTest(unittest.TestCase):
    """Issue 42: eleven SRD weapons were missing from the catalog."""

    EXPECTED = {
        'club': ('1d4', 'bludgeoning', 'simple'),
        'sickle': ('1d4', 'slashing', 'simple'),
        'blowgun': ('1', 'piercing', 'simple'),
        'flail': ('1d8', 'bludgeoning', 'martial'),
        'glaive': ('1d10', 'slashing', 'martial'),
        'greatsword': ('2d6', 'slashing', 'martial'),
        'halberd': ('1d10', 'slashing', 'martial'),
        'maul': ('2d6', 'bludgeoning', 'martial'),
        'pike': ('1d10', 'piercing', 'martial'),
        'war_pick': ('1d8', 'piercing', 'martial'),
        'whip': ('1d4', 'slashing', 'martial'),
    }

    def test_weapons_load(self):
        session = _session()
        for name, (damage, damage_type, prof) in self.EXPECTED.items():
            meta = session.load_weapon(name)
            self.assertIsNotNone(meta, f"{name} missing from items/weapons.yml")
            self.assertEqual(meta.get('damage'), damage, name)
            self.assertEqual(meta.get('damage_type'), damage_type, name)
            self.assertEqual(meta.get('proficiency_type'), [prof], name)
            self.assertEqual(meta.get('subtype'), 'weapon', name)


class HideScoringTest(unittest.TestCase):
    """Issue 43: the heuristic controller must not value hide attempts
    that the rules say auto-fail (or that are already up)."""

    def setUp(self):
        from natural20.generic_controller import GenericController
        self.session = _session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.rogue = PlayerCharacter.load(self.session, 'halfling_rogue.yml')
        self.foe = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.rogue, 'a', position=[0, 5])
        self.battle.add(self.foe, 'b', position=[2, 5])
        self.controller = GenericController(self.session)

    def test_hidden_scores_below_nothing(self):
        self.rogue.do_hide(20)
        score = self.controller._score_hide(self.rogue, self.battle, self.map,
                                            {self.foe: ((2, 5), [])})
        self.assertLess(score, 0)

    def test_hiding_in_plain_sight_scores_zero(self):
        self.assertTrue(self.map.can_see(self.foe, self.rogue))
        score = self.controller._score_hide(self.rogue, self.battle, self.map,
                                            {self.foe: ((2, 5), [])})
        self.assertEqual(score, 0.0)

    def test_hiding_out_of_sight_earns_a_real_score(self):
        self.map.remove(self.foe)
        score = self.controller._score_hide(self.rogue, self.battle, self.map,
                                            {self.foe: ((2, 5), [])})
        self.assertGreater(score, 0.1,
                           "a legal hide should beat filler bonus actions")


class WizardCantripListTest(unittest.TestCase):
    """Issue 44: Burning Hands was listed as a wizard cantrip."""

    def test_burning_hands_is_a_first_level_spell(self):
        data = yaml.safe_load(open('templates/char_classes/wizard.yml'))
        spell_list = data['spell_list']
        self.assertNotIn('burning_hands', spell_list['cantrip'])
        self.assertIn('burning_hands', spell_list['level_1'])


# ---------------------------------------------------------------------------
# Third batch (items 45-62), reported by the "Forests and Faeries" Rust-port
# team after ~1,000 AI-played games (issue #6, comment 7077995386).
# ---------------------------------------------------------------------------

class SpellSlotPaymentTest(unittest.TestCase):
    """Issue 45: the 2024 'One Spell with a Spell Slot per Turn' limit counts
    slots *expended*; free/feature casts and scrolls pay no slot."""

    def _entity(self, model):
        ruleset = SimpleNamespace(spells_per_turn_model=lambda: model)
        return SimpleNamespace(session=SimpleNamespace(ruleset=ruleset))

    def _battle(self, cast):
        return SimpleNamespace(entity_state_for=lambda e: {'casted_spells': cast})

    def test_free_cast_does_not_block_slotted_cast(self):
        from natural20.utils.spell_requirements import spells_this_turn_issue
        entity = self._entity('one_slot_per_turn')
        battle = self._battle([{'level': 1, 'resource': 'action', 'slot_paid': False}])
        self.assertIsNone(spells_this_turn_issue(entity, battle, 1, 'action'))

    def test_paid_slot_blocks_second_slotted_cast(self):
        from natural20.utils.spell_requirements import spells_this_turn_issue
        entity = self._entity('one_slot_per_turn')
        battle = self._battle([{'level': 1, 'resource': 'action', 'slot_paid': True}])
        self.assertIsNotNone(spells_this_turn_issue(entity, battle, 1, 'action'))

    def test_legacy_entries_treat_level_as_payment(self):
        from natural20.utils.spell_requirements import spells_this_turn_issue
        entity = self._entity('one_slot_per_turn')
        battle = self._battle([{'level': 1, 'resource': 'action'}])
        self.assertIsNotNone(spells_this_turn_issue(entity, battle, 2, 'action'))

    def test_2014_bonus_action_rule_still_counts_level(self):
        from natural20.utils.spell_requirements import spells_this_turn_issue
        entity = self._entity('bonus_action_spell')
        battle = self._battle([{'level': 1, 'resource': 'action', 'slot_paid': False}])
        # A non-cantrip action cast (even a free one) still blocks bonus-
        # action spells under the 2014 rule.
        self.assertIsNotNone(spells_this_turn_issue(entity, battle, 0, 'bonus_action'))


class UseSlotFreeCastChoiceTest(unittest.TestCase):
    """Issue 62: the caster can opt to spend a spell slot and keep the free
    (feature) use for later (`use_slot`)."""

    def _built_pool(self, use_slot):
        from unittest import mock
        session = _session()
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        captured = {}
        original_clone = SpellAction.clone

        def spy_clone(self):
            action = original_clone(self)
            captured['action'] = action
            return action

        action = SpellAction(session, mage, 'spell')
        action.use_slot = use_slot
        with mock.patch.object(SpellAction, 'clone', spy_clone), \
                mock.patch('natural20.utils.class_mechanics.free_cast_pool_for',
                           return_value='magic_initiate:healing_word'):
            action.build_map()['next'](('healing_word', 1))
        return captured['action'].free_cast_pool

    def test_default_prefers_free_cast(self):
        self.assertEqual(self._built_pool(False), 'magic_initiate:healing_word')

    def test_use_slot_saves_the_free_use(self):
        self.assertIsNone(self._built_pool(True))


class DodgeExpiryTest(unittest.TestCase):
    """Issue 52: Dodge/Disengage end at the start of the creature's next
    turn even when it never acts (unconscious) or never gets one (dead)."""

    def _battle_with(self):
        session = _session()
        map_ = Map(session, 'battle_sim_objects')
        battle = Battle(session, map_)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('goblin', {'name': 'g'})
        battle.add(fighter, 'a', position=[0, 5])
        battle.add(npc, 'b', position=[1, 5])
        battle.start()
        return battle, fighter

    def test_dodge_ends_when_unconscious_turn_starts(self):
        battle, fighter = self._battle_with()
        fighter.do_dodge(battle)
        self.assertTrue(fighter.dodge(battle))
        fighter.make_unconscious()
        fighter.death_saving_throw = lambda battle=None: None
        battle.set_current_turn(fighter)
        battle.start_turn()
        self.assertFalse(fighter.dodge(battle))

    def test_disengage_ends_when_dead_turn_is_skipped(self):
        battle, fighter = self._battle_with()
        state = battle.entity_state_for(fighter)
        state['statuses'].add('disengage')
        fighter.make_dead(battle=battle)
        battle.set_current_turn(fighter)
        battle.skip_dead_turns()
        self.assertNotIn('disengage', battle.entity_state_for(fighter)['statuses'])


class GridDistanceTest(unittest.TestCase):
    """Issue 48: on a grid every step (orthogonal or diagonal) counts as
    one square of distance (SRD 5.2.1 'Playing on a Grid')."""

    def test_diagonal_counts_the_same_as_a_straight_line(self):
        session = _session()
        map_ = Map(session, 'large_map')
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        map_.place((11, 2), fighter, 'A')
        self.assertEqual(map_.distance_to_square(fighter, 5, 7), 6)
        self.assertEqual(map_.distance_to_square(fighter, 11 + 3, 2 + 3), 3)
        self.assertEqual(map_.distance_to_square(fighter, 11 + 1, 2 + 1), 1)


class CreatureIsNotWallTest(unittest.TestCase):
    """Issues 47/50/51: creatures (living allies, downed allies, corpses)
    are not walls: corner-cutting keeps its diagonal, straight corridors
    can be passed through, and a dead creature never holds a square."""

    def setUp(self):
        self.session = _session()
        self.map = Map(self.session, 'large_map')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.ally = PlayerCharacter.load(self.session, 'human_fighter.yml')
        self.battle.add(self.fighter, 'a', position=[5, 5])
        self.battle.add(self.ally, 'a', position=[6, 5])
        self.battle.start()
        self.battle.set_current_turn(self.fighter)
        self.fighter.reset_turn(self.battle)

    def test_diagonal_offered_with_ally_on_the_flank(self):
        actions = self.fighter.available_actions(self.session, self.battle,
                                                 auto_target=True, map=self.map)
        paths = {tuple(map(tuple, a.move_path)) for a in actions
                 if isinstance(a, MoveAction)}
        self.assertIn(((5, 5), (6, 6)), paths)

    def test_move_through_ally_offered_and_executed(self):
        actions = self.fighter.available_actions(self.session, self.battle,
                                                 auto_target=True, map=self.map)
        through = [a for a in actions if isinstance(a, MoveAction)
                   and tuple(map(tuple, a.move_path)) == ((5, 5), (6, 5), (7, 5))]
        self.assertTrue(through, '2-square pass-through option missing')
        action = through[0]
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertEqual([7, 5], list(self.map.position_of(self.fighter)))

    def test_dead_creature_does_not_hold_its_square(self):
        npc = self.session.npc('goblin', {'name': 'corpse'})
        self.battle.add(npc, 'b', position=[8, 5])
        npc.make_dead(battle=self.battle)
        self.assertTrue(self.map.placeable(self.fighter, 8, 5, self.battle))

    def test_placeable_ignore_creature_occupants_for_path_checks(self):
        # ally occupies (6,5): normal placement refuses, path checks allow
        self.assertFalse(self.map.placeable(self.fighter, 6, 5, self.battle,
                                            squeeze=False))
        self.assertTrue(self.map.placeable(self.fighter, 6, 5, self.battle,
                                           squeeze=False,
                                           ignore_creature_occupants=True))
        self.assertTrue(self.map.passable_through(self.fighter, 6, 5, self.battle))


class LineOfSightSymmetryTest(unittest.TestCase):
    """Issue 55: Bresenham tie-breaking made A->B and B->A clip different
    wall corners, so a wall granted the unseen-attacker bonus in only one
    direction."""

    def test_paths_are_mutually_symmetric(self):
        session = _session()
        map_ = Map(session, 'battle_sim_objects')
        pairs = [((1, 1), (6, 4)), ((0, 6), (6, 0)), ((2, 2), (7, 5)),
                 ((3, 0), (5, 7)), ((0, 0), (7, 7))]
        for a, b in pairs:
            forward = map_.squares_in_path(a[0], a[1], b[0], b[1])
            backward = map_.squares_in_path(b[0], b[1], a[0], a[1])
            self.assertEqual(forward, list(reversed(backward)),
                             f'{a}->{b} asymmetric')

    def test_sight_agrees_in_both_directions_through_a_corner(self):
        session = _session()
        map_ = Map(session, 'battle_sim_objects')
        fighter_a = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        fighter_b = PlayerCharacter.load(session, 'human_fighter.yml')
        map_.place((1, 6), fighter_a, 'A')
        map_.place((6, 7), fighter_b, 'B')
        self.assertEqual(map_.line_of_sight(1, 6, 6, 7) is not None,
                         map_.line_of_sight(6, 7, 1, 6) is not None)


class DodgeRequiresSightTest(unittest.TestCase):
    """Issue 60: Dodge's disadvantage only applies against attackers the
    dodger can see; a hidden striker in the dark is not penalized."""

    def test_dodge_does_not_penalize_unseen_attacker(self):
        from natural20.weapons import compute_advantages_and_disadvantages
        session = _session()
        map_ = Map(session, 'large_map')
        battle = Battle(session, map_)
        dodger = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        striker = session.npc('goblin', {'name': 'sneak'})
        battle.add(dodger, 'a', position=[5, 5])
        battle.add(striker, 'b', position=[10, 5])
        battle.start()
        dodger.do_dodge(battle)
        self.assertTrue(dodger.dodge(battle))

        advantages, disadvantages = compute_advantages_and_disadvantages(
            session, striker, dodger, None, battle=battle,
            consume_masteries=False)
        self.assertIn('target_dodge', disadvantages)
        self.assertNotIn('unseen_attacker', advantages)

        striker.statuses.append('invisible')
        advantages, disadvantages = compute_advantages_and_disadvantages(
            session, striker, dodger, None, battle=battle,
            consume_masteries=False)
        self.assertNotIn('target_dodge', disadvantages)
        self.assertIn('unseen_attacker', advantages)


class ThunderwaveLineOfEffectTest(unittest.TestCase):
    """Issue 59: the directional cube picked up creatures behind a wall;
    areas of effect need line of effect from the origin."""

    def test_cube_skips_targets_behind_a_wall(self):
        session = _session()
        map_ = Map(session, 'large_map')
        # Wall column at x=12 (except the near goblin's square stays open)
        for y in (3, 4, 6, 7):
            map_.base_map[12][y] = '#'
        map_.base_map[12][5] = '#'
        battle = Battle(session, map_)
        caster = PlayerCharacter.load(session, 'high_elf_mage.yml')
        near = session.npc('goblin', {'name': 'near'})
        far = session.npc('goblin', {'name': 'far'})
        battle.add(caster, 'a', position=[10, 5])
        battle.add(near, 'b', position=[11, 5])   # open cube square, seen
        battle.add(far, 'b', position=[13, 5])    # behind the wall (total cover)
        battle.start()
        caster.reset_turn(battle)

        from natural20.spell.thunderwave_spell import ThunderwaveSpell
        props = session.load_spell('thunderwave')
        spell = ThunderwaveSpell(session, caster, 'ThunderwaveSpell', props)
        fake_action = SimpleNamespace(target=[13, 5], at_level=1, level=1)
        events = spell.resolve(caster, battle, fake_action, map_)
        targets = {id(e['target']) for e in events if e.get('target') is not None}
        self.assertIn(id(near), targets)
        self.assertNotIn(id(far), targets)


class BlessDeathSaveTest(unittest.TestCase):
    """Issue 53: Bless/Bane dice apply to death saving throws like any
    other saving throw."""

    def test_bless_dice_join_the_death_save(self):
        from unittest import mock
        session = _session()
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        fighter.attributes['hp'] = 0
        fighter.make_unconscious()
        original_has_effect = fighter.has_effect
        fighter.has_effect = lambda name: (name == 'bless' or
                                           original_has_effect(name))
        # Deterministic d20 stand-in that supports the DieRolls sum.
        with mock.patch('natural20.die_roll.DieRoll.roll_with_lucky',
                        classmethod(lambda cls, *a, **k: DieRoll.roll('1d4'))):
            fighter.death_saving_throw()
        # d4 + bless d4 is always < 10, so the save fails at least once.
        self.assertEqual(fighter.death_fails, 1)
        self.assertEqual(fighter.death_saves, 0)


class GroupedConcentrationSaveTest(unittest.TestCase):
    """Issue 57: one hit whose damage is split across items (weapon hit +
    riders) is a single damage instance: ONE pooled concentration save."""

    def test_one_save_for_split_damage(self):
        events = []
        session = _session(events)
        map_ = Map(session, 'large_map')
        battle = Battle(session, map_)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('goblin', {'name': 'g'})
        battle.add(fighter, 'a', position=[5, 5])
        battle.add(npc, 'b', position=[6, 5])
        battle.start()
        fighter.concentration = 'spirit_guardians_effect'
        fighter.save_throw = lambda save_type, battle=None, opts=None: \
            DieRoll.roll('50')

        hit_state = {}
        fighter.take_damage(3, battle=battle, damage_type='piercing',
                            item={'type': 'damage', 'source': npc,
                                  '_hit_state': hit_state})
        fighter.take_damage(6, battle=battle, damage_type='necrotic',
                            item={'type': 'additional_damage', 'source': npc,
                                  '_hit_state': hit_state})
        checks = [e for e in events if e.get('event') == 'concentration_check']
        self.assertEqual([], checks, 'save fired before the hit finished')

        from natural20.action import Action
        flusher = Action(session, fighter, 'test_flush')
        flusher.result = []
        battle.commit(flusher)
        checks = [e for e in events if e.get('event') == 'concentration_check']
        self.assertEqual(1, len(checks))
        # DC uses the POOLED damage: max(10, 9//2) = 10, and both earlier
        # DCs would also have been 10 -- but exactly one roll must happen.
        self.assertEqual(10, checks[0]['dc'])

    def test_split_damage_above_ten_uses_pooled_dc(self):
        events = []
        session = _session(events)
        map_ = Map(session, 'large_map')
        battle = Battle(session, map_)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('goblin', {'name': 'g'})
        battle.add(fighter, 'a', position=[5, 5])
        battle.add(npc, 'b', position=[6, 5])
        battle.start()
        # Report scenario: a well-fed caster survives the hit and just has
        # to make the one save.
        fighter.attributes['max_hp'] = 100
        fighter.attributes['hp'] = 100
        fighter.concentration = 'spirit_guardians_effect'
        fighter.save_throw = lambda save_type, battle=None, opts=None: \
            DieRoll.roll('50')
        hit_state = {}
        fighter.take_damage(11, battle=battle, damage_type='piercing',
                            item={'type': 'damage', 'source': npc,
                                  '_hit_state': hit_state})
        fighter.take_damage(13, battle=battle, damage_type='necrotic',
                            item={'type': 'additional_damage', 'source': npc,
                                  '_hit_state': hit_state})
        from natural20.action import Action
        flusher = Action(session, fighter, 'test_flush')
        flusher.result = []
        battle.commit(flusher)
        checks = [e for e in events if e.get('event') == 'concentration_check']
        self.assertEqual(1, len(checks))
        # 24 pooled damage -> DC max(10, 24//2) = 12, not two saves at DC 11
        # and DC 12.
        self.assertEqual(12, checks[0]['dc'])


class InterruptedMovementTest(unittest.TestCase):
    """Issue 58: the opportunity attack interrupts the move: it resolves
    while the mover stands on the square it is provoking from, and an
    interrupted mover ends its move there."""

    def test_mover_ends_on_the_square_the_attack_interrupted(self):
        from unittest import mock
        from natural20.actions.move_action import MoveAction
        from natural20.generic_controller import GenericController
        session = _session()
        map_ = Map(session, 'large_map')
        battle = Battle(session, map_)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        brute = session.npc('legendary_brute', {'name': 'boss'})
        battle.add(fighter, 'a', position=[16, 15])
        controller = GenericController(session)
        battle.add(brute, 'b', position=[15, 13], token='2')
        controller.register_handlers_on(brute)
        battle.start()
        fighter.reset_turn(battle)
        brute.reset_turn(battle)
        fighter.attributes['hp'] = 1

        # Walk the flank of the brute's 5 ft reach: it may retaliate when
        # the fighter leaves the adjacent square (16, 12) for (16, 11).
        move = MoveAction(session, fighter, 'move')
        move.move_path = [[16, 15], [16, 14], [16, 13], [16, 12], [16, 11]]
        # Deterministic brute attack roll so the interruption is certain.
        with mock.patch('natural20.die_roll.DieRoll.roll_with_lucky',
                        classmethod(lambda cls, *a, **k: DieRoll.roll('30'))):
            resolved = move.resolve(session, map_, {'battle': battle})
            battle.commit(resolved)

        self.assertFalse(fighter.conscious(),
                         'the opportunity attack should have dropped the mover')
        # The mover stopped where the attack caught it: it is no longer at
        # its start square, and it never finished the move.
        self.assertEqual([16, 12], list(map_.position_of(fighter)))


class ScorchingRayRetargetTest(unittest.TestCase):
    """Issue 54: rays are separate attacks; a ray aimed at a target that
    already died to an earlier ray re-aims at a living enemy instead of
    being wasted on the corpse."""

    def test_later_ray_retargets_after_the_first_kills(self):
        from unittest import mock
        events = []
        session = _session(events)
        map_ = Map(session, 'large_map')
        battle = Battle(session, map_)
        wizard = PlayerCharacter.load(session, 'high_elf_mage.yml')
        first = session.npc('goblin', {'name': 'first'})
        second = session.npc('ogre', {'name': 'second'})
        battle.add(wizard, 'a', position=[2, 5])
        battle.add(first, 'b', position=[4, 5])
        battle.add(second, 'b', position=[5, 5])
        battle.start()
        wizard.reset_turn(battle)
        first.attributes['hp'] = 1
        before = second.hp()

        from natural20.spell.wizard_spells import ScorchingRaySpell
        from natural20.action import Action
        props = session.load_spell('scorching_ray')
        spell = ScorchingRaySpell(session, wizard, 'ScorchingRaySpell', props)
        fake_action = SimpleNamespace(target=[first, first, second], at_level=2,
                                      level=2)
        with mock.patch.object(type(wizard), 'ranged_spell_attack',
                               lambda self, battle=None, props=None,
                               advantage=False, disadvantage=False:
                               DieRoll.roll('30')):
            results = spell.resolve(wizard, battle, fake_action, map_)
            wrapper = Action(session, wizard, 'spell')
            wrapper.result = list(results)
            battle.commit(wrapper)

        self.assertTrue(first.dead())
        self.assertLess(second.hp(), before,
                        'the ray that lost its target should have re-aimed')
        retargets = [e for e in events if e.get('event') == 'spell_ray_retarget']
        self.assertEqual(1, len(retargets))
        self.assertEqual('first', retargets[0].get('from_target_name'))


class HiddenMovesIntoViewTest(unittest.TestCase):
    """Issue 56: hiding ends when the hider walks into an enemy's clear
    line of sight."""

    def test_moving_into_clear_view_breaks_the_hide(self):
        from natural20.actions.move_action import MoveAction
        session = _session()
        map_ = Map(session, 'large_map')
        battle = Battle(session, map_)
        rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
        watcher = session.npc('goblin', {'name': 'watcher'})
        battle.add(rogue, 'a', position=[2, 5])
        battle.add(watcher, 'b', position=[8, 5])
        battle.start()
        rogue.reset_turn(battle)
        rogue.do_hide(15)
        self.assertTrue(rogue.hidden())

        move = MoveAction(session, rogue, 'move')
        move.move_path = [[2, 5], [3, 5], [4, 5]]
        move.resolve(session, map_, {'battle': battle})
        battle.commit(move)
        self.assertFalse(rogue.hidden(),
                         'the goblin plainly sees the new square')

    def test_hide_survives_when_still_unseen(self):
        from natural20.actions.move_action import MoveAction
        session = _session()
        map_ = Map(session, 'large_map')
        battle = Battle(session, map_)
        rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
        watcher = session.npc('goblin', {'name': 'watcher'})
        battle.add(rogue, 'a', position=[2, 5])
        battle.add(watcher, 'b', position=[20, 5])  # too far for passive sight? no: LOS is unlimited
        battle.start()
        rogue.reset_turn(battle)
        rogue.statuses.append('invisible')
        rogue.do_hide(15)
        move = MoveAction(session, rogue, 'move')
        move.move_path = [[2, 5], [3, 5]]
        move.resolve(session, map_, {'battle': battle})
        battle.commit(move)
        self.assertTrue(rogue.hidden(),
                        'an invisible hider moving in open ground is still hidden')


class FontOfMagicSlotConversionTest(unittest.TestCase):
    """Issue 61: Font of Magic offers the Sorcery Point -> spell slot
    conversion as a bonus action (SRD p.66)."""

    def _sorcerer_battle(self):
        session = _session()
        pc = PlayerCharacter.load(session, 'human_sorcerer.yml')
        map_ = Map(session, 'large_map')
        battle = Battle(session, map_)
        battle.add(pc, 'a', position=[5, 5])
        battle.start()
        battle.set_current_turn(pc)
        pc.reset_turn(battle)
        return session, pc, map_, battle

    def test_conversion_offered_and_applied(self):
        session, pc, map_, battle = self._sorcerer_battle()
        self.assertTrue(pc.class_feature('font_of_magic'))
        self.assertEqual(5, getattr(pc, 'sorcery_points', None))
        before_slots = pc.spell_slots['sorcerer'][1]
        actions = pc.available_actions(session, battle, auto_target=False)
        create = [a for a in actions if a.action_type == 'create_spell_slot']
        self.assertTrue(create, 'no slot conversion in the action menu')
        built = create[0].build_map()['next'](1)
        built.resolve(session, map_, {'battle': battle})
        battle.commit(built)
        self.assertEqual(3, pc.sorcery_points)
        self.assertEqual(before_slots + 1, pc.spell_slots['sorcerer'][1])
        self.assertEqual(0, battle.entity_state_for(pc)['bonus_action'])

    def test_hidden_when_no_points_or_bonus_action(self):
        session, pc, map_, battle = self._sorcerer_battle()
        pc.sorcery_points = 1
        self.assertNotIn('create_spell_slot',
                         [a.action_type for a in
                          pc.available_actions(session, battle, auto_target=False)])
        pc.sorcery_points = 5
        battle.consume(pc, 'bonus_action')
        self.assertNotIn('create_spell_slot',
                         [a.action_type for a in
                          pc.available_actions(session, battle, auto_target=False)])


if __name__ == '__main__':
    unittest.main()
