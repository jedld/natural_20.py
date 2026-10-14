"""Ensnaring Strike: weapon-hit restraint (2024 after-hit bonus action, 2014 next hit)."""
from natural20.actions.attack_action import AttackAction
from natural20.actions.break_free_action import BreakFreeAction
from natural20.actions.spell_action import SpellAction
from natural20.controller import Controller
from natural20.die_roll import DieRoll
from natural20.spell.ensnaring_strike_spell import EnsnaringStrikeSpell
from natural20.utils.class_feature_registry import collect_class_feature_actions
from tests.ranger_spell_helpers import Arena, forced_save
from tests.spell_cast_helpers import sticky_d20


class TakeWeaponHitSpell(Controller):
    def __init__(self, session):
        super().__init__(session)
        self.offers = []

    def select_reaction(self, entity, battle, map_obj, valid_actions, event):
        if event and event.get('type') == 'weapon_hit_spell':
            self.offers.append(valid_actions)
            return valid_actions[0] if valid_actions else None
        return None


def _arena(tmp_path, ruleset, controlled=True):
    arena = Arena(tmp_path, ruleset=ruleset, spells=['ensnaring_strike'])
    controller = None
    if controlled:
        controller = TakeWeaponHitSpell(arena.session)
        arena.battle.set_controller_for(arena.caster, controller)
    return arena, controller


def _attack(arena, target, roll):
    arena.caster.reset_turn(arena.battle)
    attack = AttackAction(arena.session, arena.caster, 'attack')
    attack.target = target
    attack.using = 'longbow'
    DieRoll.fudge(roll)
    try:
        arena.battle.execute_action(attack)
    finally:
        DieRoll.unfudge()
    return attack


def _ensnare(arena, caster, target, slot=1):
    spell = EnsnaringStrikeSpell(arena.session, caster, 'EnsnaringStrikeSpell', arena.spell('ensnaring_strike'))
    with forced_save(target, 1):
        items = spell.on_weapon_hit(caster, target, {}, slot, arena.battle)
    EnsnaringStrikeSpell.apply(arena.battle, items[0], arena.session)
    return spell, items[0]


def test_2024_after_hit_offer_restrains_on_failed_save(tmp_path):
    arena, controller = _arena(tmp_path, '5e-2024')
    assert arena.spell('ensnaring_strike')['weapon_hit']['timing'] == 'after_hit'
    _attack(arena, arena.goblin, roll=1)
    assert controller.offers == []  # a miss offers nothing

    bonus_before = arena.battle.entity_state_for(arena.caster)['bonus_action']
    with forced_save(arena.goblin, 1):
        attack = _attack(arena, arena.goblin, roll=19)
    assert controller.offers, 'a hit should offer the spell'
    assert any(i.get('type') == 'weapon_hit_spell_cast' for i in attack.result)
    assert arena.goblin.restrained() or arena.goblin.dead()
    assert isinstance(arena.caster.concentration, EnsnaringStrikeSpell)
    assert arena.caster.spell_slots['ranger'][1] == 2
    assert arena.battle.entity_state_for(arena.caster)['bonus_action'] == bonus_before - 1


def test_2024_successful_save_ends_spell(tmp_path):
    arena, _ = _arena(tmp_path, '5e-2024')
    with forced_save(arena.goblin, 30):
        _attack(arena, arena.goblin, roll=19)
    assert not arena.goblin.restrained()
    assert arena.caster.concentration is None


def test_2024_cannot_be_cast_from_the_spell_list(tmp_path):
    arena, _ = _arena(tmp_path, '5e-2024')
    assert not SpellAction.can_cast(arena.caster, arena.battle, 'ensnaring_strike')


def test_start_of_turn_damage_and_scaling(tmp_path):
    arena, _ = _arena(tmp_path, '5e-2024')
    _spell, item = _ensnare(arena, arena.caster, arena.goblin, slot=3)
    assert item['dice'] == 3 and not item['success']
    hp = arena.goblin.hp()
    arena.goblin.resolve_trigger('start_of_turn', {'battle': arena.battle})
    assert arena.goblin.hp() < hp or arena.goblin.dead()


def test_large_creatures_save_with_advantage(tmp_path):
    arena, _ = _arena(tmp_path, '5e-2024')
    spell = EnsnaringStrikeSpell(arena.session, arena.caster, 'EnsnaringStrikeSpell',
                                 arena.spell('ensnaring_strike'))
    captured = {}

    def spy(ability, battle=None, opts=None):
        captured.update(opts or {})
        return DieRoll.roll('30')

    arena.goblin.save_throw = spy
    arena.goblin.size_identifier = lambda: 'large'
    spell.on_weapon_hit(arena.caster, arena.goblin, {}, 1, arena.battle)
    assert captured.get('advantage') == ['large_creature']


def test_break_free_ends_the_spell(tmp_path):
    arena, _ = _arena(tmp_path, '5e-2024')
    _ensnare(arena, arena.caster, arena.goblin)
    assert arena.goblin.restrained()
    arena.battle.current_turn_index = arena.battle.combat_order.index(arena.goblin)
    arena.goblin.reset_turn(arena.battle)
    options = BreakFreeAction.options_for(arena.session, arena.goblin, arena.battle)
    assert len(options) == 1 and options[0].target is arena.goblin
    assert any(isinstance(a, BreakFreeAction)
               for a in arena.goblin.available_actions(arena.session, arena.battle))
    with sticky_d20(20):
        action = options[0].resolve(arena.session, arena.map, {'battle': arena.battle})
        arena.battle.commit(action)
    assert not arena.goblin.restrained()
    assert arena.caster.concentration is None


def test_break_free_offered_to_pcs_for_adjacent_allies(tmp_path):
    arena, _ = _arena(tmp_path, '5e-2024')
    _ensnare(arena, arena.goblin, arena.ally)
    actions = [a for a in collect_class_feature_actions(arena.session, arena.caster, arena.battle)
               if isinstance(a, BreakFreeAction)]
    assert [a.target for a in actions] == [arena.ally]


def test_2014_arms_on_cast_and_fires_on_next_hit(tmp_path):
    arena, _ = _arena(tmp_path, '5e-2014')
    assert arena.spell('ensnaring_strike')['weapon_hit']['timing'] == 'next_hit'
    arena.cast('ensnaring_strike', 1)
    assert isinstance(arena.caster.concentration, EnsnaringStrikeSpell)
    assert arena.caster.has_effect('weapon_hit_spell_armed')
    with forced_save(arena.goblin, 1):
        _attack(arena, arena.goblin, roll=19)
    assert arena.goblin.restrained() or arena.goblin.dead()
    assert not arena.caster.has_effect('weapon_hit_spell_armed')
    assert isinstance(arena.caster.concentration, EnsnaringStrikeSpell)
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert not arena.goblin.restrained()


def test_save_load_round_trip(tmp_path):
    arena, _ = _arena(tmp_path, '5e-2024', controlled=False)
    _ensnare(arena, arena.caster, arena.goblin, slot=2)
    session2, _battle2, _maps2 = arena.round_trip()
    goblin2 = session2.entity_by_uid(arena.goblin.entity_uid)
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    assert goblin2.restrained()
    assert goblin2.entity_event_hooks.get('start_of_turn')
    caster2.dismiss_effect(caster2.concentration)
    assert not goblin2.restrained()
