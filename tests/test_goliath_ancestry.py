"""Goliath giant ancestry (SRD 5.2) and the 2014 Stone's Endurance trait."""

import random
import shutil
from pathlib import Path

import pytest
import yaml

from natural20.actions.attack_action import AttackAction
from natural20.actions.clouds_jaunt_action import CloudsJauntAction
from natural20.actions.escape_grapple_action import EscapeGrappleAction
from natural20.actions.large_form_action import LargeFormAction
from natural20.battle import Battle
from natural20.controller import Controller
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils import giant_ancestry
from natural20.utils.serialization import Serialization

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class _Decline(Controller):
    def select_reaction(self, entity, battle, map_obj, valid_actions, event):
        return None


@pytest.fixture(autouse=True)
def _seed():
    random.seed(4242)
    yield
    for sides in (4, 6, 8, 10, 12, 20):
        DieRoll.unfudge(sides)


def _session(root='tests/fixtures'):
    return Session(root_path=str(root), event_manager=EventManager())


def _campaign_2024(tmp_path):
    dest = tmp_path / "campaign"
    shutil.copytree(FIXTURES, dest, ignore=shutil.ignore_patterns("tmp", "__pycache__", "*.pyc"))
    game_path = dest / "game.yml"
    game = yaml.safe_load(game_path.read_text(encoding="utf-8")) or {}
    game["ruleset"] = "5e-2024"
    game_path.write_text(yaml.safe_dump(game), encoding="utf-8")
    (dest / "races" / "goliath.yml").unlink()
    return dest


def _goliath(session, subrace=None, level=2, **extra):
    override = {'classes': {'paladin': level}, 'level': level, **extra}
    if subrace:
        override['subrace'] = subrace
    return PlayerCharacter.load(session, 'goliath_paladin.yml', override=override)


def _arena(session, goliath, foe_name='goblin', goliath_pos=(2, 2), foe_pos=(3, 2),
           controller=None, foe=None):
    battle_map = Map(session, 'jev_arena')
    battle = Battle(session, battle_map)
    battle.add(goliath, 'heroes', controller=controller, position=list(goliath_pos))
    foe = foe or session.npc(foe_name)
    battle.add(foe, 'foes', position=list(foe_pos))
    battle.start()
    goliath.reset_turn(battle)
    foe.reset_turn(battle)
    return battle_map, battle, foe


def _attack(session, battle, attacker, target, weapon='warhammer'):
    attack = AttackAction(session, attacker, 'attack')
    attack.target = target
    attack.using = weapon
    DieRoll.fudge(19)
    battle.execute_action(attack)
    DieRoll.unfudge()
    return attack


# --- race data / features ---------------------------------------------------

def test_2014_goliath_still_loads_with_stones_endurance():
    session = _session()
    pc = _goliath(session)
    assert pc.speed() == 30
    assert pc.class_feature('stones_endurance')
    assert not pc.class_feature('large_form')
    assert not pc.class_feature('powerful_build')
    assert 'cold' in pc.resistances
    pool = pc.get_resource('stones_endurance')
    assert pool.max_value == 1 and pool.restore_on == 'short_rest'


def test_2024_ancestry_subrace_in_2014_template_swaps_traits():
    session = _session()
    pc = _goliath(session, subrace='fire_giant', level=5)
    assert pc.class_feature('fires_burn')
    assert not pc.class_feature('stones_endurance')
    assert pc.class_feature('large_form')
    assert pc.class_feature('powerful_build')
    assert pc.speed() == 35
    assert 'cold' not in pc.resistances
    assert pc.get_resource('stones_endurance') is None


def test_large_form_gated_by_character_level():
    session = _session()
    assert not _goliath(session, subrace='hill_giant', level=4).class_feature('large_form')
    assert _goliath(session, subrace='hill_giant', level=5).class_feature('large_form')


def test_2024_overlay_goliath(tmp_path):
    session = _session(_campaign_2024(tmp_path))
    pc = _goliath(session, subrace='stone_giant', level=5)
    assert pc.speed() == 35
    assert pc.class_feature('stones_endurance')
    assert not pc.class_feature('fires_burn')
    assert 'cold' not in pc.resistances
    assert giant_ancestry.pool_name_for(pc, 'stones_endurance') == 'giant_ancestry'


def test_stones_endurance_default_uses_follow_ruleset(tmp_path):
    session = _session(_campaign_2024(tmp_path))
    pc = _goliath(session, level=5)
    pc.race_properties['race_features'] = ['stones_endurance']
    pc.race_properties.pop('resource_pools', None)
    assert giant_ancestry.feature_pool(pc, 'stones_endurance')[0] == 'giant_ancestry'
    assert session.ruleset.stones_endurance_uses_model() == 'proficiency_per_long_rest'
    assert _session().ruleset.stones_endurance_uses_model() == 'once_per_short_rest'


# --- uses pool --------------------------------------------------------------

def test_giant_ancestry_pool_is_proficiency_bonus_and_restores_on_long_rest():
    session = _session()
    pc = _goliath(session, subrace='fire_giant', level=5)
    pool = pc.get_resource('giant_ancestry')
    assert pool.max_value == pc.proficiency_bonus() == 3
    assert pool.restore_on == 'long_rest'
    assert 'giant_ancestry' in pc.character_resource_pools()
    pc.consume_resource('giant_ancestry', 3)
    assert not giant_ancestry.has_use(pc, 'fires_burn')
    pc.short_rest(None, force=True)
    assert pool.current == 0
    pc.long_rest(force=True)
    assert pool.current == 3


def test_short_rest_pool_also_refills_on_long_rest():
    session = _session()
    pc = _goliath(session)
    pc.consume_resource('stones_endurance')
    pc.long_rest(force=True)
    assert pc.get_resource('stones_endurance').current == 1


def test_pools_survive_save_load():
    session = _session()
    pc = _goliath(session, subrace='fire_giant', level=5)
    pc.consume_resource('giant_ancestry')
    restored = PlayerCharacter.from_dict(pc.to_dict())
    assert restored.get_resource('giant_ancestry').current == 2
    assert restored.class_feature('fires_burn')


# --- on-hit riders ----------------------------------------------------------

def test_fires_burn_adds_fire_damage_and_spends_use():
    session = _session()
    pc = _goliath(session, subrace='fire_giant')
    _, battle, goblin = _arena(session, pc)
    goblin.attributes['hp'] = 200
    goblin._max_hp = 200
    DieRoll.fudge(7, die_sides=10)
    attack = _attack(session, battle, pc, goblin)
    rider = [r for r in attack.result if r.get('type') == 'giant_ancestry_damage']
    assert rider and rider[0]['damage_type'] == 'fire'
    assert rider[0]['damage'].result() == 7
    # Warhammer 1d8+3 plus the 7 fire damage.
    assert 200 - goblin.hp() >= 7 + 4
    assert pc.get_resource('giant_ancestry').current == 1


def test_on_hit_rider_can_be_declined():
    session = _session()
    pc = _goliath(session, subrace='fire_giant')
    _, battle, goblin = _arena(session, pc, controller=_Decline(session))
    goblin.attributes['hp'] = 200
    attack = _attack(session, battle, pc, goblin)
    assert not [r for r in attack.result if r.get('type') == 'giant_ancestry_damage']
    assert pc.get_resource('giant_ancestry').current == 2


def test_frosts_chill_slows_target():
    session = _session()
    pc = _goliath(session, subrace='frost_giant')
    _, battle, goblin = _arena(session, pc)
    goblin.attributes['hp'] = 200
    base_speed = goblin.speed()
    _attack(session, battle, pc, goblin)
    assert goblin.speed() == base_speed - 10
    pc.reset_turn(battle)
    assert goblin.speed() == base_speed


def test_hills_tumble_prones_large_or_smaller_only():
    session = _session()
    pc = _goliath(session, subrace='hill_giant')
    _, battle, goblin = _arena(session, pc)
    goblin.attributes['hp'] = 200
    _attack(session, battle, pc, goblin)
    assert goblin.prone()

    pc2 = _goliath(session, subrace='hill_giant')
    _, battle2, ogre = _arena(session, pc2, foe_name='ogre')
    ogre.properties['size'] = 'huge'
    ogre.attributes['hp'] = 500
    _attack(session, battle2, pc2, ogre)
    assert not ogre.prone()
    assert pc2.get_resource('giant_ancestry').current == 2


# --- damage reactions -------------------------------------------------------

def test_stones_endurance_reduces_damage_and_uses_reaction():
    session = _session()
    pc = _goliath(session, subrace='stone_giant')
    pc.attributes['hp'] = 16
    _, battle, goblin = _arena(session, pc)
    DieRoll.fudge(10, die_sides=12)
    pc.take_damage(12, battle=battle, damage_type='slashing', item={'source': goblin})
    # 1d12 (10) + CON mod (+2) prevents all 12 damage.
    assert pc.hp() == 16
    assert not pc.has_reaction(battle)
    assert pc.get_resource('giant_ancestry').current == 1
    pc.take_damage(5, battle=battle, damage_type='slashing', item={'source': goblin})
    assert pc.hp() == 11


def test_2014_stones_endurance_once_per_short_rest():
    session = _session()
    pc = _goliath(session)
    pc.attributes['hp'] = 16
    _, battle, goblin = _arena(session, pc)
    DieRoll.fudge(1, die_sides=12)
    pc.take_damage(6, battle=battle, damage_type='slashing', item={'source': goblin})
    assert pc.hp() == 13
    assert pc.get_resource('stones_endurance').current == 0
    pc.reset_turn(battle)
    pc.take_damage(6, battle=battle, damage_type='slashing', item={'source': goblin})
    assert pc.hp() == 7


def test_storms_thunder_retaliates_within_60_feet_only():
    session = _session()
    pc = _goliath(session, subrace='storm_giant')
    _, battle, goblin = _arena(session, pc, foe_pos=(9, 2))
    goblin.attributes['hp'] = 50
    DieRoll.fudge(6, die_sides=8)
    pc.take_damage(3, battle=battle, damage_type='piercing', item={'source': goblin})
    assert goblin.hp() == 44
    assert not pc.has_reaction(battle)

    pc2 = _goliath(session, subrace='storm_giant')
    battle_map, battle2, goblin2 = _arena(session, pc2, goliath_pos=(0, 0), foe_pos=(9, 7))
    battle_map.feet_per_grid = 10  # 9 squares away -> 90 ft
    goblin2.attributes['hp'] = 50
    pc2.take_damage(3, battle=battle2, damage_type='piercing', item={'source': goblin2})
    assert goblin2.hp() == 50
    assert pc2.has_reaction(battle2)


# --- bonus actions ----------------------------------------------------------

def test_clouds_jaunt_teleports_and_spends_bonus_action():
    session = _session()
    pc = _goliath(session, subrace='cloud_giant')
    battle_map, battle, _ = _arena(session, pc, foe_pos=(9, 7))
    assert CloudsJauntAction.can(pc, battle)
    far = CloudsJauntAction(session, pc)
    far.target = [9, 2]  # 35 ft away
    assert not far.validate(battle_map)

    action = CloudsJauntAction(session, pc)
    action = action.build_map()['next']([6, 2])
    battle.execute_action(action)
    assert battle_map.position_of(pc) == [6, 2]
    assert pc.total_bonus_actions(battle) == 0
    assert pc.get_resource('giant_ancestry').current == 1
    assert not CloudsJauntAction.can(pc, battle)


def test_large_form_size_speed_strength_advantage_and_once_per_long_rest():
    session = _session()
    pc = _goliath(session, subrace='hill_giant', level=5)
    battle_map, battle, _ = _arena(session, pc, foe_pos=(9, 7))
    assert pc.size() == 'medium'
    assert LargeFormAction.can(pc, battle)
    available = [a for a in pc.available_actions(session, battle) if isinstance(a, LargeFormAction)]
    assert available
    action = LargeFormAction(session, pc)
    battle.execute_action(action)
    assert pc.size() == 'large'
    assert pc.speed() == 45
    occupied = [(x, y) for x in range(2, 4) for y in range(2, 4)
                if battle_map.tokens[x][y] and battle_map.tokens[x][y]['entity'] is pc]
    assert len(occupied) == 4
    assert 'large_form' in giant_ancestry.racial_check_advantage(pc, 'str')
    assert pc.athletics_check(battle).advantage
    assert pc.get_resource('large_form').current == 0

    session.game_time += 601
    pc.reset_turn(battle)
    assert pc.size() == 'medium'
    assert pc.speed() == 35
    occupied = [(x, y) for x in range(2, 4) for y in range(2, 4)
                if battle_map.tokens[x][y] and battle_map.tokens[x][y]['entity'] is pc]
    assert occupied == [(2, 2)]
    assert not LargeFormAction.can(pc, battle)
    pc.long_rest(force=True)
    pc.reset_turn(battle)
    assert LargeFormAction.can(pc, battle)


def test_large_form_needs_room():
    session = _session()
    pc = _goliath(session, subrace='hill_giant', level=5)
    _, battle, goblin = _arena(session, pc, goliath_pos=(0, 0), foe_pos=(1, 1))
    assert not LargeFormAction.can(pc, battle)


def test_large_form_effect_round_trips_through_serialization():
    session = _session()
    pc = _goliath(session, subrace='hill_giant', level=5)
    battle_map, battle, _ = _arena(session, pc, foe_pos=(9, 7))
    action = LargeFormAction(session, pc)
    battle.execute_action(action)
    data = Serialization().serialize(session, battle, [battle_map])
    restored = [x for x in Serialization().deserialize(data) if isinstance(x, Battle)][0]
    pc2 = next(e for e in restored.entities if getattr(e, 'name', None) == pc.name)
    assert pc2.size() == 'large'
    assert pc2.speed() == 45
    assert pc2.get_resource('large_form').current == 0
    assert giant_ancestry.large_form_active(pc2)


# --- Powerful Build ---------------------------------------------------------

def test_powerful_build_grapple_escape_advantage_and_capacity():
    session = _session()
    pc = _goliath(session, subrace='hill_giant', level=5)
    plain = _goliath(session)
    assert pc.carry_capacity() == plain.carry_capacity() * 2
    assert 'powerful_build' in giant_ancestry.racial_check_advantage(pc, 'str', 'escape_grapple')
    assert giant_ancestry.racial_check_advantage(plain, 'str', 'escape_grapple') == []

    _, battle, goblin = _arena(session, pc)
    pc.do_grappled_by(goblin)
    escape = EscapeGrappleAction(session, pc, 'escape_grapple')
    escape.target = goblin
    escape.resolve(session, None, {'battle': battle})
    assert escape.result[0]['source_roll'].advantage
