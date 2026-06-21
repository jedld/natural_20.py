from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from beyond_importer import _load_known_items, _load_known_spells  # noqa: E402
from natural20.event_manager import EventManager  # noqa: E402
from natural20.player_character import PlayerCharacter  # noqa: E402
from natural20.session import Session  # noqa: E402


def make_session():
    event_manager = EventManager()
    event_manager.standard_cli()
    return Session(root_path='user_levels/death_house', event_manager=event_manager)


def test_crysania_import_catalog_covers_dropped_spells_and_items():
    known_spells = _load_known_spells()
    known_items = _load_known_items()

    for spell in [
        'fireball', 'counterspell', 'lightning_bolt', 'chain_lightning',
        'disintegrate', 'maze', 'teleport', 'minor_illusion',
    ]:
        assert spell in known_spells

    for item in [
        'bag_of_holding', 'necklace_of_fireballs', 'wand_of_magic_missiles',
        'staff_of_defense', 'potion_of_healing_greater', 'spell_scroll_2nd_level',
    ]:
        assert item in known_items


def test_crysania_loads_abjuration_features_and_resources():
    character = PlayerCharacter.load(make_session(), 'characters/crysania_ddb_14154385.yml')

    assert character.name == 'Crysania'
    assert character.class_feature('arcane_ward')
    assert character.class_feature('projected_ward')
    assert character.class_feature('improved_abjuration')
    assert character.class_feature('spell_resistance')
    assert character.resource_value('arcane_ward') == 0
    assert character.get_resource('arcane_ward').max_value == 35


def test_arcane_ward_recharges_and_absorbs_damage_before_hp():
    character = PlayerCharacter.load(make_session(), 'characters/crysania_ddb_14154385.yml')
    character.create_or_recharge_arcane_ward(3)

    hp_before = character.hp()
    assert character.resource_value('arcane_ward') == 35

    character.take_damage(12, damage_type='force', item={'source': None})

    assert character.hp() == hp_before
    assert character.resource_value('arcane_ward') == 23


def test_charged_magic_items_initialize_resource_pools_and_are_usable():
    character = PlayerCharacter.load(make_session(), 'characters/crysania_ddb_14154385.yml')

    assert character.resource_value('wand_of_magic_missiles_charges') == 7
    assert character.resource_value('staff_of_defense_charges') == 10
    assert character.resource_value('necklace_of_fireballs_charges') == 6

    usable = {item['name'] for item in character.usable_items()}
    assert 'wand_of_magic_missiles' in usable
    assert 'staff_of_defense' in usable
    assert 'necklace_of_fireballs' in usable
