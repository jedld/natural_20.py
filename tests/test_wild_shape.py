import random
import copy
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.actions.wild_shape_action import (
    WildShapeAction,
    RevertWildShapeAction,
    WildShapeAttackAction,
)
from natural20.entity_class import wild_shape as ws


class TestWildShape(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        np.random.seed(7000)
        random.seed(7000)
        self.druid = PlayerCharacter.load(self.session, 'human_druid.yml')
        self.battle.add(self.druid, 'a', position=[0, 5])
        self.battle.start()
        self.druid.reset_turn(self.battle)

    # --- legality / availability ---

    def test_available_beasts_l2(self):
        self.assertEqual(set(ws.available_beasts(2)),
                         {'wolf', 'giant_rat', 'boar', 'cat'})

    def test_available_beasts_below_l2_empty(self):
        self.assertEqual(ws.available_beasts(1), ())

    def test_can_assume_legality(self):
        wolf_props = ws._load_beast_yaml(self.session, 'wolf')
        self.assertTrue(ws.can_assume(wolf_props, 2))
        # owl is CR 0 but flies — illegal at L2.
        owl_props = ws._load_beast_yaml(self.session, 'owl')
        self.assertFalse(ws.can_assume(owl_props, 2))
        # wolf is illegal below L2.
        self.assertFalse(ws.can_assume(wolf_props, 1))

    def test_action_can_when_pool_available(self):
        self.assertTrue(WildShapeAction.can(self.druid, self.battle))

    def test_action_cannot_when_pool_empty(self):
        self.druid.wild_shape_count = 0
        self.assertFalse(WildShapeAction.can(self.druid, self.battle))

    # --- transform ---

    def test_transform_into_wolf_overlays_stats(self):
        original_str = self.druid.ability_scores['str']
        original_wis = self.druid.ability_scores['wis']
        original_max_hp = self.druid.max_hp()
        ws.transform(self.druid, 'wolf')
        self.assertTrue(self.druid.is_wild_shaped())
        self.assertEqual(self.druid.wild_shape_form(), 'wolf')
        # Wolf physical stats applied; mental stats preserved.
        self.assertEqual(self.druid.ability_scores['str'], 14)
        self.assertEqual(self.druid.ability_scores['dex'], 15)
        self.assertEqual(self.druid.ability_scores['con'], 12)
        self.assertEqual(self.druid.ability_scores['wis'], original_wis)
        # HP swapped to beast HP.
        self.assertEqual(self.druid.max_hp(), 11)
        self.assertEqual(self.druid.hp(), 11)
        # Speed swapped.
        self.assertEqual(self.druid.properties['speed'], 40)
        # Beast attacks exposed.
        names = [a['name'] for a in (self.druid.npc_actions or [])]
        self.assertIn('Bite', names)
        # Original max_hp differs from beast HP (sanity).
        self.assertNotEqual(original_max_hp, 11)
        self.assertNotEqual(original_str, 14)

    def test_transform_via_action_consumes_charge(self):
        action = WildShapeAction(self.session, self.druid, 'wild_shape')
        action.target = 'wolf'
        action.resolve(self.session, self.map, opts={'battle': self.battle})
        for item in action.result:
            WildShapeAction.apply(self.battle, item, session=self.session)
        self.assertTrue(self.druid.is_wild_shaped())
        self.assertEqual(self.druid.wild_shape_count, 1)

    # --- revert ---

    def test_revert_restores_state(self):
        original_scores = copy.deepcopy(self.druid.ability_scores)
        original_max_hp = self.druid.max_hp()
        original_speed = self.druid.properties.get('speed')
        ws.transform(self.druid, 'wolf')
        ws.revert(self.druid)
        self.assertFalse(self.druid.is_wild_shaped())
        self.assertEqual(self.druid.ability_scores, original_scores)
        self.assertEqual(self.druid.max_hp(), original_max_hp)
        self.assertEqual(self.druid.properties.get('speed'), original_speed)
        self.assertEqual(self.druid.npc_actions or [], [])

    def test_zero_hp_in_beast_form_auto_reverts(self):
        original_max_hp = self.druid.max_hp()
        ws.transform(self.druid, 'wolf')  # 11 HP wolf
        # Take 15 damage -> 4 overflow onto druid form.
        self.druid.take_damage(15, battle=self.battle, damage_type='slashing')
        self.assertFalse(self.druid.is_wild_shaped())
        # Druid HP = original_max_hp - overflow.
        self.assertEqual(self.druid.hp(), original_max_hp - 4)

    def test_damage_within_beast_pool_keeps_form(self):
        ws.transform(self.druid, 'wolf')
        before = self.druid.hp()
        self.druid.take_damage(3, battle=self.battle, damage_type='piercing')
        self.assertTrue(self.druid.is_wild_shaped())
        self.assertEqual(self.druid.hp(), before - 3)

    # --- actions while wild-shaped ---

    def test_available_actions_includes_beast_attack(self):
        ws.transform(self.druid, 'wolf')
        actions = self.druid.available_actions(self.session, self.battle, auto_target=False)
        attack_kinds = [type(a).__name__ for a in actions]
        self.assertIn('WildShapeAttackAction', attack_kinds)
        # Bite is the wolf's npc_action; ensure it's plumbed through.
        bite = next(a for a in actions if isinstance(a, WildShapeAttackAction))
        self.assertEqual(bite.npc_action['name'], 'Bite')

    def test_wild_shape_attack_build_map_skips_weapon_when_npc_action_set(self):
        ws.transform(self.druid, 'wolf')
        bite = WildShapeAttackAction(self.session, self.druid, 'attack')
        bite.npc_action = self.druid.npc_actions[0]
        built = bite.build_map()
        self.assertEqual(built['param'][0]['type'], 'select_target')
        self.assertEqual(built['param'][0]['range'], 5)

    def test_available_actions_suppresses_spellcasting(self):
        ws.transform(self.druid, 'wolf')
        actions = self.druid.available_actions(self.session, self.battle, auto_target=False)
        kinds = {type(a).__name__ for a in actions}
        self.assertNotIn('SpellAction', kinds)

    def test_revert_action_only_visible_when_shaped(self):
        # Not shaped: revert action should not appear.
        actions = self.druid.available_actions(self.session, self.battle, auto_target=False)
        kinds = {type(a).__name__ for a in actions}
        self.assertNotIn('RevertWildShapeAction', kinds)
        ws.transform(self.druid, 'wolf')
        actions = self.druid.available_actions(self.session, self.battle, auto_target=False)
        kinds = {type(a).__name__ for a in actions}
        self.assertIn('RevertWildShapeAction', kinds)

    # --- persistence ---

    def test_wild_shape_state_round_trips_through_dict(self):
        ws.transform(self.druid, 'wolf')
        data = self.druid.to_dict()
        # Properties are mutated by the transform; deepcopy to keep the
        # snapshot stable.
        data = copy.deepcopy({k: v for k, v in data.items() if k != 'session'})
        data['session'] = self.session
        restored = PlayerCharacter.from_dict(data)
        self.assertTrue(restored.is_wild_shaped())
        self.assertEqual(restored.wild_shape_form(), 'wolf')
        self.assertEqual(restored.ability_scores['str'], 14)
        names = [a['name'] for a in (restored.npc_actions or [])]
        self.assertIn('Bite', names)


    # --- token swap ---

    def test_token_swaps_to_beast_form(self):
        original_token = self.druid.token()
        ws.transform(self.druid, 'wolf')
        # Wolf's token in templates/npcs/wolf.yml is ['<'].
        self.assertEqual(self.druid.token(), ['<'])
        self.assertNotEqual(self.druid.token(), original_token)

    def test_token_image_swaps_to_beast_form(self):
        ws.transform(self.druid, 'wolf')
        # Wolf has no explicit token_image; falls back to kind-based name.
        self.assertEqual(self.druid.token_image(), 'token_wolf.png')

    def test_token_restored_after_revert(self):
        original_token = copy.deepcopy(self.druid.token())
        original_token_image = self.druid.token_image()
        ws.transform(self.druid, 'wolf')
        ws.revert(self.druid)
        self.assertEqual(self.druid.token(), original_token)
        self.assertEqual(self.druid.token_image(), original_token_image)

    def test_token_round_trips_through_dict(self):
        ws.transform(self.druid, 'wolf')
        data = self.druid.to_dict()
        data = copy.deepcopy({k: v for k, v in data.items() if k != 'session'})
        data['session'] = self.session
        restored = PlayerCharacter.from_dict(data)
        # Beast token re-applied after load.
        self.assertEqual(restored.token(), ['<'])
        self.assertEqual(restored.token_image(), 'token_wolf.png')

    def test_serialized_properties_have_humanoid_token(self):
        original_token_property = copy.deepcopy(self.druid.properties.get('token'))
        original_token_image_property = self.druid.properties.get('token_image')
        ws.transform(self.druid, 'wolf')
        data = self.druid.to_dict()
        # Persisted properties should reflect the humanoid form, so a
        # save written mid-transform restores the original token visuals
        # alongside the wild-shape state.
        self.assertEqual(data['properties'].get('token'), original_token_property)
        self.assertEqual(data['properties'].get('token_image'),
                         original_token_image_property)


if __name__ == '__main__':
    unittest.main()
