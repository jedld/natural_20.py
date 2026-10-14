"""Magic Weapon: +1/+2/+3 to attack and damage with a nonmagical weapon."""
import re

from natural20.spell.magic_weapon_spell import MagicWeaponSpell, nonmagical_weapons
from natural20.weapons import damage_modifier
from tests.ranger_spell_helpers import Arena


def _flat(formula):
    match = re.search(r'([+-]\d+)$', str(formula))
    return int(match.group(1)) if match else 0


def _longbow(entity):
    return entity.session.load_weapon('longbow')


def test_2014_concentration_and_bonus_steps(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2014', spells=['magic_weapon'])
    details = arena.spell('magic_weapon')
    assert details['concentration']
    spell = MagicWeaponSpell(arena.session, arena.caster, 'MagicWeaponSpell', details)
    assert [spell.bonus_for(s) for s in (2, 3, 4, 5, 6)] == [1, 1, 2, 2, 3]


def test_2024_no_concentration_and_faster_steps(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', spells=['magic_weapon'])
    details = arena.spell('magic_weapon')
    assert not details.get('concentration')
    spell = MagicWeaponSpell(arena.session, arena.caster, 'MagicWeaponSpell', details)
    assert [spell.bonus_for(s) for s in (2, 3, 6)] == [1, 2, 3]


def test_cast_on_ally_adds_attack_and_damage(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2014', spells=['magic_weapon'])
    assert 'longbow' in nonmagical_weapons(arena.ally)
    bow = _longbow(arena.ally)
    attack_before = arena.ally.attack_roll_mod(bow)
    damage_before = _flat(damage_modifier(arena.ally, bow))
    arena.cast('magic_weapon', 4, arena.ally)
    assert arena.ally.attack_roll_mod(bow) == attack_before + 2
    assert _flat(damage_modifier(arena.ally, bow)) == damage_before + 2
    assert isinstance(arena.caster.concentration, MagicWeaponSpell)
    # Other weapons are untouched.
    sword = arena.session.load_weapon('shortsword')
    assert arena.caster.attack_roll_mod(sword) == arena.ally.attack_roll_mod(sword)


def test_2024_cast_does_not_concentrate(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', spells=['magic_weapon'])
    bow = _longbow(arena.caster)
    before = arena.caster.attack_roll_mod(bow)
    arena.cast('magic_weapon', 3, arena.caster)
    assert arena.caster.attack_roll_mod(bow) == before + 2
    assert arena.caster.concentration is None


def test_dismiss_removes_bonus(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2014', spells=['magic_weapon'])
    bow = _longbow(arena.ally)
    before = arena.ally.attack_roll_mod(bow)
    arena.cast('magic_weapon', 2, arena.ally)
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert arena.ally.attack_roll_mod(bow) == before


def test_creature_without_nonmagical_weapon_is_invalid(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2014', spells=['magic_weapon'])
    arena.ally.properties['equipped'] = []
    if hasattr(arena.ally, 'equipped'):
        arena.ally.equipped = []
    assert nonmagical_weapons(arena.ally) == []
    spell = MagicWeaponSpell(arena.session, arena.caster, 'MagicWeaponSpell', arena.spell('magic_weapon'))
    spell.validate(arena.map, arena.ally, arena.battle)
    assert spell.validation_failed()
    assert 'spell.magic_weapon.no_weapon' in repr(spell.validation_issues)


def test_save_load_round_trip(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2014', spells=['magic_weapon'])
    bow = _longbow(arena.ally)
    before = arena.ally.attack_roll_mod(bow)
    arena.cast('magic_weapon', 6, arena.ally)
    session2, _battle2, _maps2 = arena.round_trip()
    ally2 = session2.entity_by_uid(arena.ally.entity_uid)
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    assert ally2.attack_roll_mod(session2.load_weapon('longbow')) == before + 3
    caster2.dismiss_effect(caster2.concentration)
    assert ally2.attack_roll_mod(session2.load_weapon('longbow')) == before
