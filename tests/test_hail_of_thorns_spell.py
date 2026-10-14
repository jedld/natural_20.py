"""Hail of Thorns (2024 PHB expansion pack): ranged-hit burst, DEX save for half."""
from natural20.actions.attack_action import AttackAction
from natural20.controller import Controller
from natural20.die_roll import DieRoll
from natural20.spell.hail_of_thorns_spell import HailOfThornsSpell
from tests.ranger_spell_helpers import Arena, forced_save

PACK = 'players_handbook_2024'


class TakeWeaponHitSpell(Controller):
    def __init__(self, session):
        super().__init__(session)
        self.offers = []

    def select_reaction(self, entity, battle, map_obj, valid_actions, event):
        if event and event.get('type') == 'weapon_hit_spell':
            self.offers.append(valid_actions)
            return valid_actions[0] if valid_actions else None
        return None


def _arena(tmp_path, controlled=True):
    arena = Arena(tmp_path, ruleset='5e-2024', packs=[PACK], spells=['hail_of_thorns'])
    controller = None
    if controlled:
        controller = TakeWeaponHitSpell(arena.session)
        arena.battle.set_controller_for(arena.caster, controller)
    return arena, controller


def _shoot(arena, target, weapon='longbow', roll=19):
    arena.caster.reset_turn(arena.battle)
    attack = AttackAction(arena.session, arena.caster, 'attack')
    attack.target = target
    attack.using = weapon
    DieRoll.fudge(roll)
    try:
        arena.battle.execute_action(attack)
    finally:
        DieRoll.unfudge()
    return attack


def test_pack_definition_uses_2024_values(tmp_path):
    arena, _ = _arena(tmp_path, controlled=False)
    details = arena.spell('hail_of_thorns')
    assert details['spell_class'] == 'Natural20::HailOfThorns'
    assert details['weapon_hit']['timing'] == 'after_hit'
    assert details['damage_dice'] == '2d10'
    assert 'ranger' in [c.lower() for c in details['spell_list_classes']]


def test_template_stub_is_pack_only(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', spells=['hail_of_thorns'])
    assert arena.spell('hail_of_thorns')['spell_class'] == 'Natural20::ExpansionPackOnly'


def test_damage_formula_scales(tmp_path):
    arena, _ = _arena(tmp_path, controlled=False)
    spell = HailOfThornsSpell(arena.session, arena.caster, 'HailOfThornsSpell', arena.spell('hail_of_thorns'))
    assert spell.damage_formula(1) == '2d10'
    assert spell.damage_formula(3) == '4d10'


def test_ranged_hit_bursts_on_target_and_neighbors(tmp_path):
    arena, controller = _arena(tmp_path)
    hp1, hp2 = arena.goblin.hp(), arena.goblin2.hp()
    with forced_save(arena.goblin, 1), forced_save(arena.goblin2, 1):
        attack = _shoot(arena, arena.goblin)
    assert controller.offers
    thorn_items = [i for i in attack.result if i.get('trigger') == 'hail_of_thorns']
    assert {i['target'] for i in thorn_items} == {arena.goblin, arena.goblin2}
    assert arena.goblin2.hp() < hp2 or arena.goblin2.dead()
    assert arena.goblin.hp() < hp1 or arena.goblin.dead()
    assert arena.caster.spell_slots['ranger'][1] == 2
    assert arena.caster.concentration is None


def test_successful_save_halves_damage(tmp_path):
    arena, _ = _arena(tmp_path, controlled=False)
    spell = HailOfThornsSpell(arena.session, arena.caster, 'HailOfThornsSpell', arena.spell('hail_of_thorns'))
    DieRoll.fudge(10)
    try:
        with forced_save(arena.goblin2, 30):
            items = spell.on_weapon_hit(arena.caster, arena.goblin2, {}, 1, arena.battle)
    finally:
        DieRoll.unfudge()
    saved = next(i for i in items if i['target'] is arena.goblin2)
    assert saved['save_failed'] is False
    assert saved['damage'].result() == saved['damage_roll'].half().result()


def test_melee_hit_does_not_offer(tmp_path):
    arena, controller = _arena(tmp_path)
    arena.map.move_to(arena.caster, 5, 2, arena.battle)
    _shoot(arena, arena.goblin, weapon='shortsword')
    assert controller.offers == []


def test_save_load_round_trip(tmp_path):
    arena, _ = _arena(tmp_path, controlled=False)
    with forced_save(arena.goblin, 1):
        _shoot(arena, arena.goblin, roll=1)
    session2, _battle2, _maps2 = arena.round_trip()
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    assert caster2.spell_slots['ranger'][1] == arena.caster.spell_slots['ranger'][1]
    assert session2.load_spell('hail_of_thorns')['damage_dice'] == '2d10'
