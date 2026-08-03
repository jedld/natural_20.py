from natural20.battle import Battle, build_opposing_groups
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class DummySocket:
    def emit(self, *args, **kwargs):
        pass

    def start_background_task(self, target, **kwargs):
        pass


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def restore_log_snapshot(self, snapshot):
        pass


def _wild_sheep_session():
    event_manager = EventManager()
    event_manager.standard_cli()
    return Session(root_path='user_levels/wild_sheep_chase', event_manager=event_manager)


def test_map_add_applies_legend_group_to_entity():
    session = _wild_sheep_session()
    battle_map = Map(session, 'user_levels/wild_sheep_chase/maps/town_market.yml')

    mara = session.entity_by_uid('mara_bartender')
    guz = session.entity_by_uid('guz')

    assert mara is not None
    assert guz is not None
    assert mara.group == 'c'
    assert guz.group == 'b'
    assert mara.properties.get('group') == 'c'


def test_build_opposing_groups_reads_campaign_config():
    session = _wild_sheep_session()
    opposing = build_opposing_groups(session)

    assert opposing['a'] == ['b']
    assert opposing['b'] == ['a']
    assert opposing['c'] == []
    assert opposing['d'] == ['b']


def test_neutral_factions_do_not_auto_join_hostile_combat():
    from webapp.utils import GameManagement

    session = _wild_sheep_session()
    battle_map = Map(session, 'user_levels/wild_sheep_chase/maps/town_market.yml')
    pc = PlayerCharacter.load(session, 'characters/aldric_fighter.yml', override={'entity_uid': 'test_pc'})
    battle_map.add(pc, 10, 10, group='a')

    game = GameManagement(
        game_session=session,
        map_location='user_levels/wild_sheep_chase/maps/town_market.yml',
        other_maps={},
        socketio=DummySocket(),
        output_logger=DummyLogger(),
        tile_px=16,
        controllers=[],
        npc_controller='ai',
        autosave=False,
        auto_battle=True,
        system_logger=DummyLogger(),
        soundtrack=[],
    )
    game.maps = {'town_market': battle_map}

    guz = session.entity_by_uid('guz')
    mara = session.entity_by_uid('mara_bartender')
    assert guz is not None and mara is not None

    game.loop_environment(aggressive_pairs=[(pc, guz)])

    assert game.battle is not None
    combatants = set(game.battle.entities.keys())
    assert guz in combatants
    assert pc in combatants
    assert mara not in combatants


def test_battle_treats_neutral_group_as_non_opposing():
    session = _wild_sheep_session()
    battle_map = Map(session, 'user_levels/wild_sheep_chase/maps/town_market.yml')
    battle = Battle(session, [battle_map])

    pc = PlayerCharacter.load(session, 'characters/aldric_fighter.yml', override={'entity_uid': 'test_pc'})
    mara = session.entity_by_uid('mara_bartender')
    guz = session.entity_by_uid('guz')

    battle.add(pc, 'a')
    battle.add(mara, 'c')
    battle.add(guz, 'b')

    assert not battle.opposing(pc, mara)
    assert battle.opposing(pc, guz)


def _battle_sim_game():
    from webapp.utils import GameManagement

    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    session.game_properties.setdefault('groups', {
        'a': {'enemies': ['b']},
        'b': {'enemies': ['a']},
    })
    battle_map = Map(session, 'battle_sim_objects')
    game = GameManagement(
        game_session=session,
        map_location='battle_sim_objects',
        other_maps={},
        socketio=DummySocket(),
        output_logger=DummyLogger(),
        tile_px=16,
        controllers=[],
        npc_controller='ai',
        autosave=False,
        auto_battle=True,
        system_logger=DummyLogger(),
        soundtrack=[],
    )
    game.maps = {'battle_sim_objects': battle_map}
    return session, battle_map, game


def test_only_witnessing_npcs_join_on_aggressive_action():
    session, battle_map, game = _battle_sim_game()
    pc = PlayerCharacter.load(session, 'high_elf_mage.yml', override={'entity_uid': 'witness_test_pc'})
    victim = session.npc('goblin', {'name': 'Victim'})
    witness = session.npc('goblin', {'name': 'Witness'})
    distant = session.npc('goblin', {'name': 'Distant'})

    battle_map.add(pc, 1, 1, group='a')
    battle_map.add(victim, 3, 1, group='b')
    battle_map.add(witness, 4, 1, group='b')
    battle_map.add(distant, 6, 6, group='b')

    assert battle_map.can_see(witness, victim)
    assert not battle_map.can_see(distant, victim)
    assert not game._npc_witnesses_fight(distant, {pc, victim}, battle_map)

    game.loop_environment(aggressive_pairs=[(pc, victim)])

    assert game.battle is not None
    combatants = set(game.battle.entities.keys())
    assert pc in combatants
    assert victim in combatants
    assert witness in combatants
    assert distant not in combatants


def test_npc_can_join_combat_by_hearing_without_line_of_sight():
    from unittest.mock import patch

    session, battle_map, game = _battle_sim_game()
    pc = PlayerCharacter.load(session, 'high_elf_mage.yml', override={'entity_uid': 'hearing_test_pc'})
    victim = session.npc('goblin', {'name': 'Victim'})
    listener = session.npc('goblin', {'name': 'Listener'})

    battle_map.add(pc, 1, 1, group='a')
    battle_map.add(victim, 2, 1, group='b')
    battle_map.add(listener, 1, 2, group='b')

    real_can_see = battle_map.can_see

    def _can_see(observer, observed):
        if observer is listener and observed in {pc, victim}:
            return False
        return real_can_see(observer, observed)

    with patch.object(battle_map, 'can_see', side_effect=_can_see):
        assert not battle_map.can_see(listener, victim)
        assert game._npc_witnesses_fight(listener, {pc, victim}, battle_map)
        game.loop_environment(aggressive_pairs=[(pc, victim)])

    assert game.battle is not None
    combatants = set(game.battle.entities.keys())
    assert listener in combatants


def test_party_pcs_join_combat_across_maps():
    session, battle_map, game = _battle_sim_game()
    other_map = Map(session, 'battle_sim_4')
    game.maps['battle_sim_4'] = other_map

    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml', override={'entity_uid': 'party_fighter'})
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml', override={'entity_uid': 'party_mage'})
    victim = session.npc('goblin', {'name': 'Victim'})

    battle_map.add(fighter, 1, 1, group='a')
    other_map.add(mage, 2, 2, group='a')
    battle_map.add(victim, 3, 1, group='b')

    assert game.get_map_for_entity(fighter) is battle_map
    assert game.get_map_for_entity(mage) is other_map

    game.loop_environment(aggressive_pairs=[(fighter, victim)])

    assert game.battle is not None
    combatants = set(game.battle.entities.keys())
    assert fighter in combatants
    assert mage in combatants
    assert victim in combatants
