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
