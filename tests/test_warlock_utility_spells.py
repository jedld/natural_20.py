"""Blink, Blade Ward, Plant Growth, Seeming, Comprehend Languages, the detect
spells, Contact Other Plane (SRD) plus Thunder Step / Synaptic Static
(Xanathar's pack) and Summon Fiend (PHB 2024 pack)."""
from natural20.die_roll import DieRoll
from natural20.npc import Npc
from natural20.spell.disguise_self_spell import disguise_of
from natural20.utils.attack_penalties import penalty_dice
from natural20.utils.language_comprehension import understands_language
from natural20.utils.monster_traits import trigger_death_burst
from natural20.utils.off_plane import off_plane
from tests.ranger_spell_helpers import Arena, forced_save

SRD = ['blink', 'blade_ward', 'plant_growth', 'seeming', 'comprehend_languages',
       'detect_evil_and_good', 'detect_poison_and_disease', 'contact_other_plane']
PACK = ['thunder_step', 'synaptic_static', 'summon_fiend']


def _arena(tmp_path, ruleset='5e-2014', packs=(), spells=SRD, battle=True):
    return Arena(tmp_path, ruleset=ruleset, packs=packs, caster='wizard', spells=list(spells),
                 with_battle=battle)


class _fixed_roll:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self._orig = DieRoll.roll
        value = self.value
        orig = self._orig

        def fake(expr, *args, **kwargs):
            if str(expr).startswith('1d20') or str(expr).startswith('1d6'):
                return orig(str(value), *args, **kwargs)
            return orig(expr, *args, **kwargs)
        DieRoll.roll = staticmethod(fake)
        return self

    def __exit__(self, *exc):
        DieRoll.roll = self._orig
        return False


def test_blink_vanishes_on_high_roll_and_returns(tmp_path):
    arena = _arena(tmp_path)
    arena.cast('blink', 3)
    with _fixed_roll(15):
        arena.caster.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert off_plane(arena.caster)
    assert not arena.caster.allow_targeting()
    arena.caster.resolve_trigger('start_of_turn', {'battle': arena.battle})
    assert not off_plane(arena.caster)
    with _fixed_roll(3):
        arena.caster.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert not off_plane(arena.caster)


def test_blink_2024_uses_d6(tmp_path):
    arena = _arena(tmp_path, ruleset='5e-2024')
    assert arena.spell('blink')['blink'] == {'die': 'd6', 'success_min': 4}


def test_blade_ward_2014_grants_weapon_resistance(tmp_path):
    arena = _arena(tmp_path)
    arena.cast('blade_ward', 0)
    assert arena.caster.resistant_to('slashing')
    assert not arena.caster.resistant_to('fire')


def test_blade_ward_2024_penalizes_attackers(tmp_path):
    arena = _arena(tmp_path, ruleset='5e-2024', packs=['players_handbook_2024'])
    assert arena.spell('blade_ward')['blade_ward']['mode'] == 'attack_penalty'
    arena.cast('blade_ward', 0)
    assert penalty_dice(arena.caster, 'targeted_attack_penalty', {'attacker': arena.goblin}) == ['1d4']
    assert not arena.caster.resistant_to('slashing')
    assert arena.caster.concentration is not None


def test_plant_growth_quadruples_movement_cost(tmp_path):
    arena = _arena(tmp_path)
    arena.cast('plant_growth', 3, [10, 10])
    assert arena.map.extra_terrain_cost(10, 10) == 2
    assert arena.map.difficult_terrain(arena.goblin, 10, 10)
    assert arena.map.extra_terrain_cost(0, 0) == 2  # radius 100 ft covers the whole field


def test_seeming_disguises_caster_and_ally(tmp_path):
    arena = _arena(tmp_path)
    arena.cast('seeming', 5, (arena.caster, arena.ally))
    assert disguise_of(arena.caster) is not None
    assert disguise_of(arena.ally) is not None


def test_comprehend_languages_understands_any_tongue(tmp_path):
    arena = _arena(tmp_path, battle=False)
    assert not understands_language(arena.caster, 'goblin')
    arena.cast('comprehend_languages', 1)
    assert understands_language(arena.caster, 'goblin')


def test_detect_evil_and_good_senses_fiends(tmp_path):
    arena = _arena(tmp_path)
    arena.goblin.properties['race'] = ['fiend']
    events = []
    arena.session.event_manager.register_event_listener('detect_creatures', lambda e: events.append(e))
    arena.cast('detect_evil_and_good', 1)
    names = [f['entity'] for f in events[-1]['found']]
    assert arena.goblin in names and arena.goblin2 not in names


def test_detect_poison_senses_poisoned_creature(tmp_path):
    arena = _arena(tmp_path)
    arena.goblin2.statuses.append('poisoned')
    events = []
    arena.session.event_manager.register_event_listener('detect_creatures', lambda e: events.append(e))
    arena.cast('detect_poison_and_disease', 1)
    assert [f['entity'] for f in events[-1]['found']] == [arena.goblin2]


def test_contact_other_plane_failure_harms_and_incapacitates(tmp_path):
    arena = _arena(tmp_path, battle=False)
    hp = arena.caster.hp()
    with forced_save(arena.caster, 1):
        action = arena.cast('contact_other_plane', 5)
    assert action.result[0]['success'] is False
    assert arena.caster.hp() < hp
    assert 'insanity' in arena.caster.statuses


def test_contact_other_plane_auto_succeeds_from_free_cast(tmp_path):
    arena = _arena(tmp_path, battle=False)
    from natural20.spell.detection_spells import _free_cast_flag
    from unittest.mock import patch
    with patch('natural20.spell.detection_spells._free_cast_flag', return_value=True):
        action = arena.cast('contact_other_plane', 5)
    assert action.result[0]['success'] is True and action.result[0]['auto'] is True
    assert callable(_free_cast_flag)


def test_thunder_step_teleports_and_booms(tmp_path):
    arena = _arena(tmp_path, packs=['xanathars_guide'], spells=PACK)
    adjacent = arena.ally
    hp = adjacent.hp()
    with forced_save(adjacent, 1):
        arena.cast('thunder_step', 3, [2, 10])
    assert arena.map.position_of(arena.caster) == [2, 10]
    assert adjacent.hp() < hp


def test_thunder_step_ignores_objects(tmp_path):
    from natural20.item_library.object import Object
    arena = _arena(tmp_path, packs=['xanathars_guide'], spells=PACK)
    chest = Object(arena.session, arena.map, {'name': 'Chest', 'max_hp': 10, 'token': 'C'})
    arena.session.register_entity(chest)
    arena.map.add(chest, 4, 2, 'b')
    chest_hp = chest.hp()
    with forced_save(arena.ally, 1):
        arena.cast('thunder_step', 3, [2, 10])
    assert arena.map.position_of(arena.caster) == [2, 10]
    assert chest.hp() == chest_hp


def test_synaptic_static_muddles_on_failed_save(tmp_path):
    arena = _arena(tmp_path, packs=['xanathars_guide'], spells=PACK)
    with forced_save(arena.goblin, 1), forced_save(arena.goblin2, 30):
        arena.cast('synaptic_static', 5, [6, 2])
    assert 'muddled' in arena.goblin.statuses or arena.goblin.dead()
    if not arena.goblin.dead():
        assert penalty_dice(arena.goblin, 'attack_roll_penalty') == ['1d6']
        assert penalty_dice(arena.goblin, 'concentration_save_penalty') == ['1d6']
        with forced_save(arena.goblin, 30):
            arena.goblin.resolve_trigger('end_of_turn', {'battle': arena.battle})
        assert 'muddled' not in arena.goblin.statuses
        assert penalty_dice(arena.goblin, 'attack_roll_penalty') == []
    assert 'muddled' not in arena.goblin2.statuses


def test_summon_fiend_scales_with_slot_level(tmp_path):
    arena = _arena(tmp_path, ruleset='5e-2024', packs=['players_handbook_2024'], spells=PACK)
    arena.caster.spell_slots['wizard'][7] = 1
    arena.cast('summon_fiend', 7, 'demon', [2, 5])
    spirit = next(e for e in arena.battle.entities if e.properties.get('summon_name') == 'summon_fiend')
    assert spirit.max_hp() == 65
    assert spirit.armor_class() == 19
    assert spirit.properties['multiattack'] == [{'any_of': ['bite'], 'count': 3}]
    bite = spirit.properties['actions'][0]
    assert bite['attack'] == arena.caster.spell_attack_modifier_for(arena.spell('summon_fiend'))
    assert bite['damage_die'] == '1d12+10'
    assert not arena.battle.opposing(arena.caster, spirit)
    order = arena.battle.combat_order
    assert order.index(spirit) == order.index(arena.caster) + 1
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert spirit not in arena.battle.entities


def test_demon_spirit_death_throes(tmp_path):
    arena = _arena(tmp_path, ruleset='5e-2024', packs=['players_handbook_2024'], spells=PACK)
    arena.cast('summon_fiend', 6, 'demon', [5, 2])
    spirit = next(e for e in arena.battle.entities if e.properties.get('summon_name') == 'summon_fiend')
    assert spirit.properties['death_throes']['dc'] == arena.caster.spell_save_dc('intelligence')
    before = {e: e.hp() for e in (arena.caster, arena.ally, arena.goblin, arena.goblin2)}
    hit = trigger_death_burst(spirit, arena.battle)
    assert hit
    assert all(e.hp() < before[e] or e.dead() for e in hit)


def test_magic_resistance_grants_save_advantage(tmp_path):
    arena = _arena(tmp_path)
    goblin = Npc(arena.session, 'goblin', {'name': 'mr', 'overrides': {'attributes': ['magic_resistance']}})
    roll = goblin.save_throw('wisdom', arena.battle, {'is_magical': True})
    assert roll.advantage
