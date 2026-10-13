"""Spirit Guardians, Revivify, Mass Healing Word, Call Lightning and Sleet Storm."""
import random
import unittest

from natural20.actions.call_lightning_bolt_action import CallLightningBoltAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.call_lightning_spell import CallLightningEffect
from natural20.utils.action_builder import autobuild
from natural20.utils.pointless_actions import is_pointless
from natural20.utils.spell_loader import load_spell_class, spell_is_implemented

SPELLS = ('spirit_guardians', 'revivify', 'mass_healing_word', 'call_lightning', 'sleet_storm')


def force_save(entity, value):
    original = entity.save_throw

    def fixed(ability, battle=None, opts=None):
        roll = original(ability, battle, opts)
        roll.rolls = [value]
        return roll

    entity.save_throw = fixed


class Level3SpellBase(unittest.TestCase):
    def setUp(self):
        random.seed(4242)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'maps/empty_map')
        self.battle = Battle(self.session, self.map)
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin', {'name': 'Goblin'})
        self.map.add(self.cleric, 1, 1)
        self.map.add(self.ally, 0, 2)
        self.map.add(self.goblin, 2, 2)
        self.battle.add(self.cleric, 'a', add_to_initiative=True)
        self.battle.add(self.ally, 'a', add_to_initiative=True)
        self.battle.add(self.goblin, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.cleric, self.ally, self.goblin])
        self.cleric.reset_turn(self.battle)
        self.cleric.spell_slots.setdefault('cleric', {})[3] = 2
        for spell in ('spirit_guardians', 'revivify', 'mass_healing_word'):
            self.cleric.properties.setdefault('prepared_spells', []).append(spell)

    def cast(self, caster, spell, target, level=3):
        action = SpellAction.build(self.session, caster)['next']([spell, level])['next'](target)
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        return action


class TestCatalog(unittest.TestCase):
    def test_yaml_loader_and_class_lists(self):
        session = Session(root_path='templates', event_manager=EventManager())
        for spell in SPELLS:
            props = session.load_spell(spell)
            self.assertEqual(props['level'], 3, spell)
            self.assertTrue(spell_is_implemented(spell, props), spell)
        for klass in ('SpiritGuardiansSpell', 'RevivifySpell', 'MassHealingWordSpell',
                      'CallLightningSpell', 'SleetStormSpell'):
            self.assertIsNotNone(load_spell_class(klass))
        import yaml
        cleric = yaml.safe_load(open('templates/char_classes/cleric.yml'))['spell_list']['level_3']
        for spell in ('spirit_guardians', 'revivify', 'mass_healing_word'):
            self.assertIn(spell, cleric)
        druid = yaml.safe_load(open('templates/char_classes/druid.yml'))['spell_list']['level_3']
        self.assertIn('call_lightning', druid)
        self.assertIn('sleet_storm', druid)


class TestSpiritGuardians(Level3SpellBase):
    def test_enemy_starting_turn_in_area_takes_damage_but_ally_does_not(self):
        self.cast(self.cleric, 'spirit_guardians', [1, 1])
        self.assertEqual(getattr(self.cleric.concentration, 'id', None), 'spirit_guardians')
        force_save(self.goblin, 1)
        goblin_hp, ally_hp = self.goblin.hp(), self.ally.hp()
        self.battle.trigger_event('start_of_turn', self.battle, {'target': self.ally})
        self.battle.trigger_event('start_of_turn', self.battle, {'target': self.goblin})
        self.assertLess(self.goblin.hp(), goblin_hp)
        self.assertEqual(self.ally.hp(), ally_hp)

    def test_struck_at_most_once_per_turn(self):
        self.cast(self.cleric, 'spirit_guardians', [1, 1])
        zone = self.battle.active_zones[0]
        self.goblin.attributes['hp'] = 500
        self.goblin.properties['max_hp'] = 500
        force_save(self.goblin, 1)
        self.assertTrue(zone.strike(self.goblin, 'turn_start'))
        self.assertEqual(zone.strike(self.goblin, 'enter'), [])

    def test_area_slows_enemies_only_and_follows_caster(self):
        self.cast(self.cleric, 'spirit_guardians', [1, 1])
        self.assertTrue(self.map.difficult_terrain(self.goblin, 3, 1, self.battle))
        self.assertFalse(self.map.difficult_terrain(self.ally, 3, 1, self.battle))
        zone = self.battle.active_zones[0]
        self.assertFalse(zone.contains((5, 5)))
        self.map.move_to(self.cleric, 4, 4, self.battle)
        self.assertTrue(zone.contains((5, 5)))

    def test_ending_concentration_removes_zone(self):
        self.cast(self.cleric, 'spirit_guardians', [1, 1])
        self.cleric.dismiss_effect(self.cleric.concentration)
        self.assertFalse(self.battle.active_zones)
        self.assertFalse(self.map.difficult_terrain(self.goblin, 3, 1, self.battle))

    def test_recasting_while_held_is_pointless(self):
        self.cast(self.cleric, 'spirit_guardians', [1, 1])
        self.cleric.reset_turn(self.battle)
        recast = SpellAction.build(self.session, self.cleric)['next'](['spirit_guardians', 3])['next']([1, 1])
        self.assertTrue(is_pointless(self.battle, self.cleric, recast))


class TestRevivify(Level3SpellBase):
    def test_needs_diamond_and_revives_recent_ally(self):
        self.ally.make_dead()
        self.assertFalse(SpellAction.can_cast(self.cleric, self.battle, 'revivify'))
        self.cleric.add_item('diamond', 1)
        self.assertTrue(SpellAction.can_cast(self.cleric, self.battle, 'revivify'))
        options = [a for a in autobuild(self.session, SpellAction, self.cleric, self.battle)
                   if getattr(a.spell_action, 'name', '') == 'RevivifySpell']
        self.assertEqual([list(a.target) for a in options], [[0, 2]])
        self.cast(self.cleric, 'revivify', [0, 2])
        self.assertFalse(self.ally.dead())
        self.assertEqual(self.ally.hp(), 1)
        self.assertEqual(self.cleric.item_count('diamond'), 0)

    def test_too_long_dead_cannot_be_targeted(self):
        self.ally.make_dead()
        self.cleric.add_item('diamond', 1)
        self.session.game_time += 120
        options = [a for a in autobuild(self.session, SpellAction, self.cleric, self.battle)
                   if getattr(a.spell_action, 'name', '') == 'RevivifySpell']
        self.assertEqual(options, [])
        self.cast(self.cleric, 'revivify', [0, 2])
        self.assertTrue(self.ally.dead())

    def test_enemy_corpses_not_offered_to_ai(self):
        self.goblin.make_dead()
        self.cleric.add_item('diamond', 1)
        options = [a for a in autobuild(self.session, SpellAction, self.cleric, self.battle)
                   if getattr(a.spell_action, 'name', '') == 'RevivifySpell']
        self.assertEqual(options, [])


class TestMassHealingWord(Level3SpellBase):
    def test_ai_option_heals_every_wounded_ally_at_once(self):
        self.ally.attributes['hp'] = 3
        self.cleric.attributes['hp'] = self.cleric.max_hp() - 4
        options = [a for a in autobuild(self.session, SpellAction, self.cleric, self.battle)
                   if getattr(a.spell_action, 'name', '') == 'MassHealingWordSpell']
        self.assertEqual(len(options), 1)
        self.assertEqual(set(options[0].target), {self.ally, self.cleric})
        action = options[0]
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertGreater(self.ally.hp(), 3)
        self.assertEqual(self.battle.entity_state_for(self.cleric)['bonus_action'], 0)

    def test_no_option_when_nobody_is_hurt(self):
        options = [a for a in autobuild(self.session, SpellAction, self.cleric, self.battle)
                   if getattr(a.spell_action, 'name', '') == 'MassHealingWordSpell']
        self.assertEqual(options, [])


class TestCallLightning(Level3SpellBase):
    def setUp(self):
        super().setUp()
        self.cleric.spell_slots['druid'] = {3: 2}
        self.cleric.properties['prepared_spells'].append('call_lightning')

    def _druid_cast(self, target):
        action = SpellAction.build(self.session, self.cleric)['next'](['call_lightning', 3])['next'](target)
        self.assertEqual(action.spellcasting_class, 'druid')
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        return action

    def test_needs_open_sky(self):
        spell = self.session.load_spell('call_lightning')
        from natural20.utils.spell_requirements import environment_issue
        self.map.properties['outdoors'] = False
        self.assertEqual(environment_issue(self.cleric, spell, self.battle), 'no open sky overhead')
        self.map.properties['ceiling_height'] = 120
        self.assertIsNone(environment_issue(self.cleric, spell, self.battle))
        self.map.properties.pop('ceiling_height')
        self.map.properties['outdoors'] = True
        self.assertIsNone(environment_issue(self.cleric, spell, self.battle))

    def test_bolt_then_follow_up_bolt_next_turn(self):
        self.map.properties['outdoors'] = True
        force_save(self.goblin, 1)
        self.goblin.attributes['hp'] = 200
        self.goblin.properties['max_hp'] = 200
        self._druid_cast([2, 2])
        self.assertLess(self.goblin.hp(), 200)
        storm = self.cleric.concentration
        self.assertIsInstance(storm, CallLightningEffect)
        self.assertEqual(storm.bolt_dice(), '3d10')
        self.assertFalse(CallLightningBoltAction.can(self.cleric, self.battle))

        self.battle.round += 1
        self.cleric.reset_turn(self.battle)
        self.assertTrue(CallLightningBoltAction.can(self.cleric, self.battle))
        bolts = autobuild(self.session, CallLightningBoltAction, self.cleric, self.battle)
        self.assertTrue(bolts)
        hp = self.goblin.hp()
        bolt = bolts[0]
        bolt.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(bolt)
        self.assertLess(self.goblin.hp(), hp)
        self.assertFalse(CallLightningBoltAction.can(self.cleric, self.battle))

    def test_storm_adds_a_die(self):
        self.map.properties['outdoors'] = True
        self.map.properties['weather'] = 'thunderstorm'
        self._druid_cast([2, 2])
        self.assertEqual(self.cleric.concentration.bolt_dice(), '4d10')

    def test_bolt_must_land_under_cloud(self):
        self.map.properties['outdoors'] = True
        self._druid_cast([2, 2])
        bolt = CallLightningBoltAction(self.session, self.cleric, 'call_lightning_bolt')
        bolt.validate(self.map, [2 + 13, 2])
        self.assertTrue(bolt.errors)
        bolt.validate(self.map, [2 + 5, 2])
        self.assertFalse(bolt.errors)


class TestSleetStorm(unittest.TestCase):
    def setUp(self):
        random.seed(99)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'maps/empty_map')
        self.battle = Battle(self.session, self.map)
        self.mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.goblin = self.session.npc('goblin', {'name': 'Goblin'})
        self.map.add(self.mage, 0, 0)
        self.map.add(self.goblin, 4, 4)
        self.battle.add(self.mage, 'a', add_to_initiative=True)
        self.battle.add(self.goblin, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.mage, self.goblin])
        self.mage.reset_turn(self.battle)
        self.mage.spell_slots.setdefault('wizard', {})[3] = 2
        self.mage.properties.setdefault('spellbook', []).append('sleet_storm')
        self.mage.properties.setdefault('prepared_spells', []).append('sleet_storm')

    def _cast(self, center):
        action = SpellAction.build(self.session, self.mage)['next'](['sleet_storm', 3])['next'](center)
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)

    def test_area_is_icy_obscured_and_trips_creatures(self):
        self._cast([4, 4])
        self.assertTrue(self.map.difficult_terrain(self.goblin, 5, 5, self.battle))
        self.assertTrue(self.map._light_builder.obscuring_gas_at(4, 4))
        force_save(self.goblin, 1)
        self.battle.trigger_event('start_of_turn', self.battle, {'target': self.goblin})
        self.assertTrue(self.goblin.prone())

    def test_concentrating_creature_in_storm_can_lose_concentration(self):
        self._cast([2, 2])
        self.assertEqual(getattr(self.mage.concentration, 'id', None), 'sleet_storm')
        force_save(self.mage, 1)
        zone = self.battle.active_zones[0]
        zone.on_turn_start(self.mage)
        self.assertIsNone(self.mage.concentration)
        self.assertFalse(self.battle.active_zones)
        self.assertFalse(self.map._light_builder.obscuring_gas_at(2, 2))


class TestDomainSpellsUseClericSlots(Level3SpellBase):
    def test_life_domain_revivify_castable_without_preparing(self):
        self.cleric.properties['prepared_spells'].remove('revivify')
        self.cleric.properties['classes']['cleric'] = 5
        self.cleric.add_item('diamond', 1)
        self.assertIn('revivify', self.cleric.prepared_spells())
        spell = self.session.load_spell('revivify')
        self.assertIn('cleric', self.cleric.spell_list_classes_for(spell))
        self.assertTrue(SpellAction.can_cast(self.cleric, self.battle, 'revivify'))


class TestPersistentZonesSurviveSaveLoad(Level3SpellBase):
    CASES = (
        ('spirit_guardians', [1, 1], 'SpiritGuardiansZone', False),
        ('sleet_storm', [6, 6], 'SleetStormZone', True),
        ('stinking_cloud', [6, 6], 'StinkingCloudZone', True),
        ('grease', [2, 2], 'GreaseZone', True),
    )

    @staticmethod
    def _zone_tiles(battle_map):
        return [o for col in battle_map.objects for cell in col for o in cell
                if getattr(o, 'zone', None) is not None]

    def _round_trip(self):
        from natural20.utils.serialization import Serialization
        serializer = Serialization()
        _, battle, maps = serializer.deserialize(serializer.serialize(self.session, self.battle, [self.map]))
        battle_map = maps[0] if isinstance(maps, list) else list(maps.values())[0]
        caster = next(e for e in battle.entities if e.name == self.cleric.name)
        return battle, battle_map, caster

    def test_zones_and_tiles_restore_and_dismiss(self):
        for spell, target, zone_class, has_tiles in self.CASES:
            with self.subTest(spell=spell):
                self.setUp()
                self.cast(self.cleric, spell, target)
                battle, battle_map, caster = self._round_trip()
                self.assertEqual([type(z).__name__ for z in battle.active_zones], [zone_class])
                zone = battle.active_zones[0]
                tiles = self._zone_tiles(battle_map)
                self.assertEqual(bool(tiles), has_tiles)
                self.assertTrue(all(t.zone is zone and t.map is battle_map for t in tiles))
                if caster.concentration is not None:
                    self.assertIs(getattr(caster.concentration, 'zone', zone), zone)
                    caster.dismiss_effect(caster.concentration)
                    self.assertFalse(battle.active_zones)
                    self.assertFalse(self._zone_tiles(battle_map))

    def test_call_lightning_storm_survives_save_load(self):
        self.cleric.spell_slots['druid'] = {3: 2}
        self.cast(self.cleric, 'call_lightning', [6, 6])
        _, _, caster = self._round_trip()
        self.assertIsInstance(caster.concentration, CallLightningEffect)
        self.assertIs(caster.concentration.source, caster)
        self.assertEqual(list(caster.concentration.center), [6, 6])


class TestTempestDomainGetsNewSpells(unittest.TestCase):
    def test_oogway_style_tempest_cleric_auto_prepares_domain_spells(self):
        import os
        path = 'user_levels/death_house'
        if not os.path.exists(os.path.join(path, 'characters', 'Oogway.yml')):
            self.skipTest('death_house campaign not checked out')
        session = Session(root_path=path, event_manager=EventManager())
        pc = PlayerCharacter.load(session, 'characters/Oogway.yml')
        prepared = pc.prepared_spells()
        self.assertIn('call_lightning', prepared)
        self.assertIn('sleet_storm', prepared)
        for spell in ('thunderwave', 'call_lightning', 'sleet_storm'):
            self.assertIn('cleric', pc.spell_list_classes_for(session.load_spell(spell)), spell)


if __name__ == '__main__':
    unittest.main()
