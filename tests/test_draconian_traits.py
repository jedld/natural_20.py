"""Generic monster mechanics added for the draconians: innate spellcasting,
NPC area-save abilities with recharge, chain death throes with a timed
condition, aura type/perception filters, glide, Dimension Door and Sending."""
import os

import pytest

from natural20.actions.npc_area_action import NpcAreaAction, area_configs, is_ready, roll_recharges
from natural20.actions.spell_action import SpellAction
from natural20.die_roll import DieRoll
from natural20.effects.timed_condition_effect import TimedConditionEffect
from natural20.generic_controller import GenericController
from natural20.map_stack_descent import glide_reduction_ft, preview_fall_damage
from natural20.utils.innate_spellcasting import innate_attack_bonus, innate_save_dc, pool_name
from natural20.utils.monster_traits import trigger_death_burst
from natural20.utils.spell_requirements import missing_materials
from tests.ranger_spell_helpers import Arena, forced_save

INNATE = {
    'ability': 'charisma', 'dc': 14, 'attack': 6, 'no_material': True,
    'at_will': ['mage_hand', 'invisibility'],
    'per_day': {2: ['dimension_door', 'sending'], 1: ['web']},
}

BREATH = {
    'name': 'noxious_breath', 'label': 'Noxious Breath', 'type': 'area_save',
    'shape': 'cone', 'range': 30, 'save': 'constitution', 'dc': 14,
    'damage_die': '6d6', 'damage_type': 'poison', 'recharge': '5-6',
    'on_fail': ['exhaustion:1'],
    'success_immunity': {'key': 'noxious_breath', 'hours': 24},
}


class _fixed_d6:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self._orig = DieRoll.roll
        orig, value = self._orig, self.value

        def fake(expr, *args, **kwargs):
            if str(expr) == '1d6':
                return orig(str(value), *args, **kwargs)
            return orig(expr, *args, **kwargs)
        DieRoll.roll = staticmethod(fake)
        return self

    def __exit__(self, *exc):
        DieRoll.roll = self._orig
        return False


def _arena(tmp_path, **props):
    arena = Arena(tmp_path, caster='wizard', spells=[])
    goblin = arena.goblin
    goblin.properties.update(props)
    if 'innate_spellcasting' in props:
        from natural20.utils.innate_spellcasting import ensure_innate_pools
        ensure_innate_pools(goblin)
    return arena


def _goblin_turn(arena):
    arena.battle.current_turn_index = arena.battle.combat_order.index(arena.goblin)
    arena.goblin.reset_turn(arena.battle)


def _breath(arena, target=(2, 2)):
    action = NpcAreaAction(arena.session, arena.goblin, 'npc_area_ability', {'ability': 'noxious_breath'})
    action.target = list(target)
    action.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(action)
    return action


# --- innate spellcasting ---------------------------------------------------

def test_innate_spells_are_prepared_with_fixed_dc(tmp_path):
    arena = _arena(tmp_path, innate_spellcasting=INNATE)
    goblin = arena.goblin
    assert {'mage_hand', 'invisibility', 'dimension_door', 'sending', 'web'} <= set(goblin.prepared_spells())
    assert innate_save_dc(goblin) == 14
    assert goblin.spell_save_dc('charisma') == 14
    assert innate_attack_bonus(goblin) == 6
    assert goblin.resources[pool_name('dimension_door')].current == 2
    assert goblin.resources[pool_name('web')].current == 1


def test_innate_per_day_casts_spend_their_pool_and_at_will_is_free(tmp_path):
    arena = _arena(tmp_path, innate_spellcasting=INNATE)
    goblin = arena.goblin
    _goblin_turn(arena)
    arena.cast('dimension_door', 4, [12, 12], caster=goblin)
    assert arena.map.position_of(goblin) == [12, 12]
    assert goblin.resources[pool_name('dimension_door')].current == 1
    arena.cast('invisibility', 2, goblin, caster=goblin)
    assert 'invisible' in goblin.statuses
    assert all(pool.current == pool.max_value for name, pool in goblin.resources.items()
               if name != pool_name('dimension_door'))


def test_innate_casting_ignores_material_components(tmp_path):
    arena = _arena(tmp_path, innate_spellcasting=INNATE)
    web = dict(arena.session.load_spell('web'), id='web')
    assert missing_materials(arena.goblin, web) == []


# --- area-save abilities with recharge -------------------------------------

def test_area_save_entries_are_not_attacks(tmp_path):
    arena = _arena(tmp_path)
    goblin = arena.goblin
    goblin.properties['actions'] = list(goblin.npc_actions) + [BREATH]
    goblin.npc_actions = goblin.properties['actions']
    names = [a['name'] for a in goblin.attack_options(arena.battle)]
    assert names and 'noxious_breath' not in names
    assert [c['name'] for c in area_configs(goblin)] == ['noxious_breath']


def test_breath_cone_damages_saves_and_adds_exhaustion_or_immunity(tmp_path):
    arena = _arena(tmp_path, actions=[BREATH])
    _goblin_turn(arena)
    ally_hp, wizard_hp = arena.ally.hp(), arena.caster.hp()
    with forced_save(arena.ally, 1), forced_save(arena.caster, 30):
        action = _breath(arena)
    hit = {item['target'] for item in action.result if item.get('type') == 'npc_area_damage'}
    assert {arena.ally, arena.caster} <= hit
    assert arena.goblin2 not in hit
    assert arena.ally.hp() < ally_hp and arena.caster.hp() < wizard_hp
    assert arena.ally.exhaustion_level() == 1
    assert arena.caster.exhaustion_level() == 0
    assert 'noxious_breath' in arena.caster.attributes['ability_immunities']
    assert not is_ready(arena.goblin, BREATH)
    assert arena.goblin.total_actions(arena.battle) == 0

    arena.goblin.attributes['recharge_spent'] = []
    _goblin_turn(arena)
    action = _breath(arena)
    immune = [item['target'] for item in action.result if item.get('type') == 'npc_area_immune']
    assert immune == [arena.caster]


def test_recharge_roll_readies_the_ability(tmp_path):
    arena = _arena(tmp_path, actions=[BREATH])
    arena.goblin.attributes['recharge_spent'] = ['noxious_breath']
    with _fixed_d6(4):
        roll_recharges(arena.goblin, arena.battle)
    assert not is_ready(arena.goblin, BREATH)
    with _fixed_d6(5):
        roll_recharges(arena.goblin, arena.battle)
    assert is_ready(arena.goblin, BREATH)


def test_breath_is_offered_and_scored_by_the_ai(tmp_path):
    arena = _arena(tmp_path, actions=[BREATH])
    _goblin_turn(arena)
    options = [a for a in arena.goblin.available_actions(arena.session, arena.battle)
               if isinstance(a, NpcAreaAction)]
    assert options and all(a.target is not None for a in options)
    best = max(options, key=lambda a: a.ai_value(arena.battle))
    assert best.ai_value(arena.battle) > 0
    scored = GenericController(arena.session)._sort_actions_with_scores(arena.goblin, arena.battle, options)
    assert scored and scored[0][1] > 0
    arena.goblin.attributes['recharge_spent'] = ['noxious_breath']
    assert not NpcAreaAction.can(arena.goblin, arena.battle)


# --- death throes -----------------------------------------------------------

def test_chain_death_throes_stun_until_end_of_next_turn(tmp_path):
    config = {'targeting': 'chain', 'range': 30, 'arc_range': 15, 'arc_targets': 2,
              'save': 'dexterity', 'dc': 14, 'damage_die': '2d8', 'damage_type': 'lightning',
              'on_fail_condition': 'stunned'}
    arena = _arena(tmp_path, death_throes=config)
    arena.map.move_to(arena.goblin2, 14, 14, arena.battle)  # out of range
    with forced_save(arena.ally, 1), forced_save(arena.caster, 1):
        hit = trigger_death_burst(arena.goblin, arena.battle)
    assert hit == [arena.ally, arena.caster]  # nearest creature, then an arc 5 ft from it
    assert 'stunned' in arena.caster.statuses
    assert 'stunned' in arena.ally.statuses
    arena.ally.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert 'stunned' not in arena.ally.statuses


def test_timed_condition_on_own_turn_lasts_through_next_turn(tmp_path):
    arena = _arena(tmp_path)
    caster = arena.caster  # first in initiative, so it is the current turn
    TimedConditionEffect.apply_to(caster, 'stunned', source=arena.goblin, battle=arena.battle)
    caster.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert 'stunned' in caster.statuses
    caster.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert 'stunned' not in caster.statuses


def test_stunned_creatures_fail_str_dex_saves_and_are_easier_to_hit(tmp_path):
    arena = _arena(tmp_path)
    TimedConditionEffect.apply_to(arena.ally, 'stunned', battle=arena.battle)
    from natural20.spell.extensions.save_check import SaveCheck
    assert not SaveCheck.make(arena.ally, 'dexterity', 1, battle=arena.battle).passed
    from natural20.weapons import compute_advantages_and_disadvantages
    advantages, _ = compute_advantages_and_disadvantages(
        arena.session, arena.goblin, arena.ally, {}, battle=arena.battle)
    assert 'target_stunned' in advantages


def test_timed_condition_survives_save_load(tmp_path):
    arena = _arena(tmp_path)
    TimedConditionEffect.apply_to(arena.ally, 'stunned', source=arena.goblin, battle=arena.battle)
    session2, battle2, _ = arena.round_trip()
    ally = session2.entity_by_uid('ally')
    assert 'stunned' in ally.statuses
    ally.resolve_trigger('end_of_turn', {'battle': battle2})
    assert 'stunned' not in ally.statuses


# --- auras ------------------------------------------------------------------

AURA = {'name': 'aura_of_command', 'range': 20, 'creature_types': ['draconian'],
        'requires': ['see', 'hear'], 'condition_immunity': ['charmed'],
        'condition_save_advantage': ['frightened']}


def test_aura_covers_only_matching_creature_types_that_perceive_the_owner(tmp_path):
    arena = _arena(tmp_path, auras=[AURA], race=['monstrosity', 'draconian'])
    goblin2 = arena.goblin2
    assert not goblin2.immune_to_condition('charmed')
    goblin2.properties['race'] = ['draconian']
    assert goblin2.immune_to_condition('charmed')
    assert goblin2.save_throw('wisdom', arena.battle, {'condition': 'frightened'}).advantage
    goblin2.statuses.append('deafened')
    assert not goblin2.immune_to_condition('charmed')


# --- glide ------------------------------------------------------------------

def test_glide_reduces_fall_damage(tmp_path):
    arena = _arena(tmp_path, glide={'fall_reduction_ft': 100})
    goblin = arena.goblin
    assert glide_reduction_ft(goblin) == 100
    assert preview_fall_damage(goblin, '4d6', fall_ft=40)['mitigated']
    assert preview_fall_damage(goblin, '15d6', fall_ft=150)['die'] == '5d6'
    goblin.statuses.append('stunned')
    assert glide_reduction_ft(goblin) == 0


# --- spells -----------------------------------------------------------------

def test_dimension_door_needs_no_line_of_sight(tmp_path):
    arena = _arena(tmp_path)
    spell = arena.session.load_spell('dimension_door')
    assert spell['require_los'] is False and spell['range'] == 500
    action = arena.build('dimension_door', 4, [14, 14])
    action.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(action)
    assert arena.map.position_of(arena.caster) == [14, 14]


def test_sending_logs_a_message(tmp_path):
    arena = _arena(tmp_path)
    events = []
    arena.session.event_manager.register_event_listener('sending', lambda e: events.append(e))
    action = arena.build('sending', 3, arena.goblin)
    action.message = 'Report to the camp.'
    action.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(action)
    assert events and events[0]['target'] is arena.goblin
    assert events[0]['message'] == 'Report to the camp.'


# --- campaign NPCs ------------------------------------------------------------

DRAGONLANCE = os.path.join(os.path.dirname(__file__), '..', 'user_levels', 'dragonlance')


@pytest.mark.skipif(not os.path.isdir(os.path.join(DRAGONLANCE, 'npcs')), reason='campaign submodule missing')
@pytest.mark.parametrize('npc_type', ['aurak_draconian', 'bozak_draconian', 'drayan'])
def test_draconian_npcs_load(npc_type):
    from natural20.session import Session
    session = Session(root_path=DRAGONLANCE)
    npc = session.npc(npc_type)
    assert npc.prepared_spells()
    assert npc.properties.get('death_throes')
    if npc_type != 'bozak_draconian':
        assert npc.spell_save_dc('charisma') == 14
        assert area_configs(npc)
