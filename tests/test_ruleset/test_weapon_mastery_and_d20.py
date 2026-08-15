"""Weapon mastery and D20 Test ruleset integration tests."""

import shutil
from pathlib import Path

import yaml

from natural20.session import Session
from natural20.weapon_mastery import can_use_mastery, weapon_masteries
from natural20.yaml_loader import load_campaign_yaml

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _campaign(tmp_path, ruleset: str):
    dest = tmp_path / "campaign"
    shutil.copytree(
        FIXTURES,
        dest,
        ignore=shutil.ignore_patterns("tmp", "__pycache__", "*.pyc"),
    )
    game_path = dest / "game.yml"
    with game_path.open("r", encoding="utf-8") as fh:
        game = yaml.safe_load(fh) or {}
    game["ruleset"] = ruleset
    with game_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(game, fh)
    return dest


def test_weapons_overlay_adds_push_under_2024(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    weapons = load_campaign_yaml(root, "items", "weapons")
    assert "push" in weapon_masteries(weapons.get("pike"))
    assert "push" in weapon_masteries(weapons.get("warhammer"))
    assert "sap" in weapon_masteries(weapons.get("longsword"))


def test_weapons_mastery_inert_under_2014(tmp_path):
    root = _campaign(tmp_path, "5e-2014")
    session = Session(str(root))
    weapon = session.load_weapon("longsword")

    class E:
        def __init__(self, sess):
            self.session = sess
            self.properties = {"known_weapon_masteries": ["sap"]}

        def class_feature(self, _):
            return False

    assert can_use_mastery(E(session), weapon, "sap") is False


def test_exhaustion_d20_penalty_2024(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    from natural20.player_character import PlayerCharacter

    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter.set_exhaustion_level(2)
    assert fighter.d20_test_modifier() == -4
    # Saving throw modifier includes exhaustion
    roll = fighter.save_throw("strength")
    # Just ensure roll builds; modifier path exercised
    assert roll is not None


def test_exhaustion_no_penalty_2014(tmp_path):
    root = _campaign(tmp_path, "5e-2014")
    session = Session(str(root))
    from natural20.player_character import PlayerCharacter

    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter.set_exhaustion_level(3)
    assert fighter.d20_test_modifier() == 0


def test_surprise_initiative_disadvantage_flag_2024(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    from natural20.player_character import PlayerCharacter

    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter.set_surprised(True)
    assert session.ruleset.surprise_model() == "initiative_disadvantage"
    # Smoke: rolls without error
    assert fighter.initiative() is not None


def test_2014_longsword_has_no_mastery_leak(tmp_path):
    root = _campaign(tmp_path, "5e-2014")
    weapons = load_campaign_yaml(root, "items", "weapons")
    assert weapon_masteries(weapons.get("longsword")) == []


def test_2024_class_overlays_grant_weapon_mastery(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    for klass in ("fighter", "barbarian", "paladin", "ranger", "rogue"):
        local = root / "char_classes" / f"{klass}.yml"
        if local.is_file():
            local.unlink()
    session = Session(str(root))
    classes = session.load_classes()
    assert "weapon_mastery" in (classes.get("fighter") or {}).get("class_features", [])
    assert "weapon_mastery" in (classes.get("barbarian") or {}).get("class_features", [])
    assert "weapon_mastery" in (classes.get("paladin") or {}).get("class_features", [])
    assert "weapon_mastery" in (classes.get("ranger") or {}).get("class_features", [])
    assert "weapon_mastery" in (classes.get("rogue") or {}).get("class_features", [])
    assert (classes.get("fighter") or {}).get("weapon_mastery_known") == 3
    assert (classes.get("rogue") or {}).get("weapon_mastery_known") == 2


def _battle_pair(session):
    from natural20.battle import Battle
    from natural20.map import Map
    from natural20.player_character import PlayerCharacter

    battle_map = Map(session, "maps/empty_map")
    battle = Battle(session, battle_map)
    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    target = PlayerCharacter.load(session, "human_bard.yml")
    battle.add(fighter, "a", position=(1, 1), token="F")
    battle.add(target, "b", position=(2, 1), token="T")
    battle.start()
    fighter.reset_turn(battle)
    target.reset_turn(battle)
    return battle, battle_map, fighter, target


def test_push_moves_target(tmp_path):
    from natural20.actions.attack_action import AttackAction

    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    battle, battle_map, fighter, target = _battle_pair(session)
    AttackAction.apply(battle, {
        "type": "weapon_mastery_push",
        "source": fighter,
        "target": target,
        "distance": 10,
    })
    assert battle_map.entity_or_object_pos(target) == [4, 1]


def test_topple_knocks_prone(tmp_path):
    from natural20.actions.attack_action import AttackAction

    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    battle, _map, fighter, target = _battle_pair(session)
    assert not target.prone()
    AttackAction.apply(battle, {
        "type": "weapon_mastery_topple",
        "source": fighter,
        "target": target,
    })
    assert target.prone()


def test_slow_expires_at_attacker_start_of_turn(tmp_path):
    from natural20.actions.attack_action import AttackAction
    from natural20.weapon_mastery import resolve_mastery_on_hit

    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    battle, _map, fighter, target = _battle_pair(session)
    fighter.properties["known_weapon_masteries"] = ["slow"]
    weapon = session.load_weapon("longbow")
    action = AttackAction(session, fighter, "attack")
    action.using = "longbow"
    action.target = target
    base_speed = target.speed()
    resolve_mastery_on_hit(action, battle, target, weapon, True, 4)
    assert target.speed() == max(0, base_speed - 10)
    fighter.reset_turn(battle)
    assert int(getattr(target, "_mastery_slow_ft", 0) or 0) == 0
    assert target.speed() == base_speed


def test_optional_push_skipped_when_declined(tmp_path):
    from natural20.actions.attack_action import AttackAction
    from natural20.weapon_mastery import resolve_mastery_on_hit

    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    battle, _map, fighter, target = _battle_pair(session)
    fighter.properties["known_weapon_masteries"] = ["push"]
    weapon = session.load_weapon("pike")
    action = AttackAction(session, fighter, "attack")
    action.using = "pike"
    action.target = target
    action.add_reaction("weapon_mastery_push", fighter, None)
    results = resolve_mastery_on_hit(action, battle, target, weapon, True, 5)
    assert not any(item.get("type") == "weapon_mastery_push" for item in results)


def test_known_mastery_list_gates_properties(tmp_path):
    from natural20.weapon_mastery import can_use_mastery

    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    from natural20.player_character import PlayerCharacter

    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter.properties["known_weapon_masteries"] = ["sap"]
    longsword = session.load_weapon("longsword")
    pike = session.load_weapon("pike")
    assert can_use_mastery(fighter, longsword, "sap") is True
    assert can_use_mastery(fighter, pike, "push") is False


def test_mastery_state_round_trips_on_pc(tmp_path):
    from natural20.player_character import PlayerCharacter

    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter._sap_next_attack = True
    fighter._mastery_slow_ft = 10
    fighter._vex_advantage_vs = {"target-uid": True}
    data = fighter.to_dict()
    restored = PlayerCharacter.from_dict(data)
    assert restored._sap_next_attack is True
    assert restored._mastery_slow_ft == 10
    assert restored._vex_advantage_vs.get("target-uid") is True


def test_attack_label_includes_mastery(tmp_path):
    from natural20.actions.attack_action import AttackAction

    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    from natural20.player_character import PlayerCharacter

    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter.properties["known_weapon_masteries"] = ["vex"]
    action = AttackAction(session, fighter, "attack")
    action.using = "rapier"
    label = action.label()
    assert "Vex" in label


def test_weapon_mastery_combat_log_handler():
    from natural20.event_manager import EventManager
    from natural20.player_character import PlayerCharacter

    logs = []

    class Capture:
        def log(self, msg, event=None, visibility=None):
            logs.append(msg)

    manager = EventManager(output_logger=Capture())
    manager.standard_cli()
    session = Session(root_path="tests/fixtures", event_manager=manager)
    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    manager.received_event({
        "event": "weapon_mastery",
        "mastery": "sap",
        "source": fighter,
        "target": fighter,
    })
    assert logs
    assert "Sap" in logs[-1]
