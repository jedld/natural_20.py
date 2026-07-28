"""Tests for campaign day/night schedule."""

from natural20.time_of_day import (
    clock_position,
    load_time_of_day_config,
    resolve_map_background_image,
    resolve_time_of_day,
    world_time_context_lines,
)


def test_load_time_of_day_defaults():
    cfg = load_time_of_day_config({})
    assert cfg['enabled'] is True
    assert cfg['day_length_seconds'] == 86400
    assert len(cfg['phases']) >= 4


def test_resolve_morning_phase():
    cfg = load_time_of_day_config({})
    # start_at 08:00 + 2 hours => morning
    state = resolve_time_of_day(2 * 3600, cfg)
    assert state.phase_id in ('morning', 'dawn', 'afternoon')
    assert 'AM' in state.clock_label or 'PM' in state.clock_label


def test_night_phase_wrap():
    cfg = load_time_of_day_config({})
    # midnight-ish: start_at 8h means game_time 16h => 00:00 next cycle... 
    # game_time 0 + start 28800 => 08:00 day 1
    _, hour = clock_position(0, cfg)
    assert 7.9 < hour < 8.1
    state = resolve_time_of_day(16 * 3600, cfg)  # +16h => midnight
    assert state.is_night is True


def test_override_phase():
    cfg = load_time_of_day_config({})
    state = resolve_time_of_day(0, cfg, override_phase_id='dusk')
    assert state.phase_id == 'dusk'


def test_resolve_map_background_images():
    props = {
        'background_image': 'default.jpg',
        'background_images': {'day': 'town_day.jpg', 'night': 'town_night.jpg'},
    }
    from natural20.time_of_day import TimeOfDayState

    day_state = TimeOfDayState(
        phase_id='morning',
        phase_label='Morning',
        illumination=1.0,
        background_key='day',
        clock_hour=10.0,
        clock_label='10:00 AM',
        period_label='Morning',
        is_night=False,
        game_time=0,
        day_number=1,
    )
    assert resolve_map_background_image(props, day_state) == 'town_day.jpg'

    night_state = TimeOfDayState(
        phase_id='night',
        phase_label='Night',
        illumination=0.1,
        background_key='night',
        clock_hour=2.0,
        clock_label='2:00 AM',
        period_label='Night',
        is_night=True,
        game_time=0,
        day_number=1,
    )
    assert resolve_map_background_image(props, night_state) == 'town_night.jpg'


def test_world_time_context_lines():
    from natural20.time_of_day import TimeOfDayState

    state = TimeOfDayState(
        phase_id='afternoon',
        phase_label='Afternoon',
        illumination=1.0,
        background_key='day',
        clock_hour=14.0,
        clock_label='2:00 PM',
        period_label='Afternoon',
        is_night=False,
        game_time=123,
        day_number=2,
    )
    lines = world_time_context_lines(state)
    assert any('2:00 PM' in line for line in lines)
    assert any('Afternoon' in line for line in lines)
