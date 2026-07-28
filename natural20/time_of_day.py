"""Campaign clock phases (day/night) derived from monotonic game_time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DEFAULT_DAY_LENGTH_SECONDS = 24 * 60 * 60
DEFAULT_START_AT_SECONDS = 8 * 60 * 60  # 08:00 on the first in-game day

DEFAULT_PHASES: List[Dict[str, Any]] = [
    {'id': 'night', 'label': 'Night', 'from_hour': 0, 'to_hour': 5, 'illumination': 0.12, 'background_key': 'night', 'is_night': True},
    {'id': 'dawn', 'label': 'Dawn', 'from_hour': 5, 'to_hour': 7, 'illumination': 0.45, 'background_key': 'dawn', 'is_night': False},
    {'id': 'morning', 'label': 'Morning', 'from_hour': 7, 'to_hour': 12, 'illumination': 0.95, 'background_key': 'day', 'is_night': False},
    {'id': 'afternoon', 'label': 'Afternoon', 'from_hour': 12, 'to_hour': 17, 'illumination': 1.0, 'background_key': 'day', 'is_night': False},
    {'id': 'dusk', 'label': 'Dusk', 'from_hour': 17, 'to_hour': 20, 'illumination': 0.5, 'background_key': 'dusk', 'is_night': False},
    {'id': 'night', 'label': 'Night', 'from_hour': 20, 'to_hour': 24, 'illumination': 0.12, 'background_key': 'night', 'is_night': True},
]


@dataclass(frozen=True)
class TimeOfDayState:
    phase_id: str
    phase_label: str
    illumination: float
    background_key: str
    clock_hour: float
    clock_label: str
    period_label: str
    is_night: bool
    game_time: int
    day_number: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            'phase_id': self.phase_id,
            'phase_label': self.phase_label,
            'illumination': self.illumination,
            'background_key': self.background_key,
            'clock_hour': self.clock_hour,
            'clock_label': self.clock_label,
            'period_label': self.period_label,
            'is_night': self.is_night,
            'game_time': self.game_time,
            'day_number': self.day_number,
        }


def load_time_of_day_config(game_properties: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    props = game_properties or {}
    block = props.get('time_of_day') or {}
    if not isinstance(block, dict):
        block = {}

    try:
        day_length = int(block.get('day_length_seconds') or DEFAULT_DAY_LENGTH_SECONDS)
    except (TypeError, ValueError):
        day_length = DEFAULT_DAY_LENGTH_SECONDS
    day_length = max(60, day_length)

    try:
        start_at = int(block.get('start_at_seconds', DEFAULT_START_AT_SECONDS))
    except (TypeError, ValueError):
        start_at = DEFAULT_START_AT_SECONDS

    phases = block.get('phases')
    if not isinstance(phases, list) or not phases:
        phases = DEFAULT_PHASES

    normalized: List[Dict[str, Any]] = []
    for entry in phases:
        if not isinstance(entry, dict):
            continue
        phase_id = str(entry.get('id') or entry.get('phase') or '').strip()
        if not phase_id:
            continue
        try:
            from_hour = float(entry.get('from_hour', 0))
            to_hour = float(entry.get('to_hour', 24))
        except (TypeError, ValueError):
            continue
        try:
            illumination = float(entry.get('illumination', 1.0))
        except (TypeError, ValueError):
            illumination = 1.0
        normalized.append({
            'id': phase_id,
            'label': str(entry.get('label') or phase_id.replace('_', ' ').title()),
            'from_hour': from_hour,
            'to_hour': to_hour,
            'illumination': max(0.0, min(1.0, illumination)),
            'background_key': str(entry.get('background_key') or phase_id),
            'is_night': bool(entry.get('is_night', phase_id in ('night', 'midnight'))),
        })

    if not normalized:
        normalized = list(DEFAULT_PHASES)

    return {
        'enabled': bool(block.get('enabled', True)),
        'day_length_seconds': day_length,
        'start_at_seconds': start_at,
        'phases': normalized,
    }


def _hour_in_phase(hour: float, from_hour: float, to_hour: float) -> bool:
    hour = hour % 24.0
    from_hour = from_hour % 24.0
    to_hour = to_hour % 24.0
    if from_hour == to_hour:
        return True
    if from_hour < to_hour:
        return from_hour <= hour < to_hour
    return hour >= from_hour or hour < to_hour


def _format_clock_label(hour: float) -> str:
    whole = int(hour) % 24
    minutes = int(round((hour - int(hour)) * 60)) % 60
    suffix = 'AM' if whole < 12 else 'PM'
    display_hour = whole % 12
    if display_hour == 0:
        display_hour = 12
    return f'{display_hour}:{minutes:02d} {suffix}'


def _period_label(phase_id: str, phase_label: str) -> str:
    return phase_label or phase_id.replace('_', ' ')


def clock_position(game_time: int, config: Dict[str, Any]) -> tuple[int, float]:
    """Return (day_number, hour_of_day 0-24) for game_time."""
    day_length = int(config.get('day_length_seconds') or DEFAULT_DAY_LENGTH_SECONDS)
    start_at = int(config.get('start_at_seconds') or 0)
    total = int(game_time or 0) + start_at
    day_number = total // day_length + 1
    seconds_into_day = total % day_length
    hour = (seconds_into_day / day_length) * 24.0
    return day_number, hour


def resolve_time_of_day(
    game_time: int,
    config: Dict[str, Any],
    *,
    override_phase_id: Optional[str] = None,
) -> TimeOfDayState:
    """Resolve the active phase for game_time."""
    if not config.get('enabled', True):
        return TimeOfDayState(
            phase_id='day',
            phase_label='Day',
            illumination=1.0,
            background_key='day',
            clock_hour=12.0,
            clock_label='12:00 PM',
            period_label='Day',
            is_night=False,
            game_time=int(game_time or 0),
            day_number=1,
        )

    day_number, hour = clock_position(game_time, config)
    phases = config.get('phases') or DEFAULT_PHASES

    if override_phase_id:
        for phase in phases:
            if str(phase.get('id')) == str(override_phase_id):
                return TimeOfDayState(
                    phase_id=str(phase['id']),
                    phase_label=str(phase.get('label') or phase['id']),
                    illumination=float(phase.get('illumination', 1.0)),
                    background_key=str(phase.get('background_key') or phase['id']),
                    clock_hour=hour,
                    clock_label=_format_clock_label(hour),
                    period_label=_period_label(str(phase['id']), str(phase.get('label') or '')),
                    is_night=bool(phase.get('is_night')),
                    game_time=int(game_time or 0),
                    day_number=day_number,
                )

    for phase in phases:
        if _hour_in_phase(hour, float(phase.get('from_hour', 0)), float(phase.get('to_hour', 24))):
            return TimeOfDayState(
                phase_id=str(phase['id']),
                phase_label=str(phase.get('label') or phase['id']),
                illumination=float(phase.get('illumination', 1.0)),
                background_key=str(phase.get('background_key') or phase['id']),
                clock_hour=hour,
                clock_label=_format_clock_label(hour),
                period_label=_period_label(str(phase['id']), str(phase.get('label') or '')),
                is_night=bool(phase.get('is_night')),
                game_time=int(game_time or 0),
                day_number=day_number,
            )

    fallback = phases[0]
    return TimeOfDayState(
        phase_id=str(fallback.get('id') or 'day'),
        phase_label=str(fallback.get('label') or 'Day'),
        illumination=float(fallback.get('illumination', 1.0)),
        background_key=str(fallback.get('background_key') or 'day'),
        clock_hour=hour,
        clock_label=_format_clock_label(hour),
        period_label=_period_label(str(fallback.get('id') or 'day'), str(fallback.get('label') or '')),
        is_night=bool(fallback.get('is_night')),
        game_time=int(game_time or 0),
        day_number=day_number,
    )


def resolve_map_background_image(map_properties: Dict[str, Any], state: TimeOfDayState) -> Optional[str]:
    """Pick a map background filename for the active time-of-day phase."""
    props = map_properties or {}
    images = props.get('background_images') or {}
    if isinstance(images, dict):
        for key in (state.background_key, state.phase_id, 'day' if not state.is_night else 'night'):
            candidate = images.get(key)
            if candidate:
                return str(candidate)

    if state.is_night and props.get('background_image_night'):
        return str(props['background_image_night'])
    if not state.is_night and props.get('background_image_day'):
        return str(props['background_image_day'])
    legacy = props.get('background_image')
    return str(legacy) if legacy else None


def world_time_context_lines(state: TimeOfDayState) -> List[str]:
    """Short lines suitable for NPC / DM LLM prompts."""
    return [
        f'Current world time: {state.clock_label} (day {state.day_number} of the campaign).',
        f'Time of day: {state.period_label} ({state.phase_label}).',
        f'It is currently {"night" if state.is_night else "daylight"}.',
    ]
