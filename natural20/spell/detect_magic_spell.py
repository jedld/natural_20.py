"""Detect Magic — concentration divination that reveals magical auras."""

from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.utils.magical_aura import DETECT_MAGIC_RANGE_FT


class DetectMagicEffect:
    """Active Detect Magic on the caster (concentration)."""

    def __init__(self, source, duration_seconds: int = 600):
        self.source = source
        self.duration = duration_seconds
        self.action = None

    @property
    def id(self):
        return 'detect_magic'

    def __str__(self):
        return 'Detect Magic'


class DetectMagicSpell(Spell):
    """Sense magic within 30 feet; visible auras show school of magic."""

    def build_map(self, orig_action):
        def set_self(_target):
            action = orig_action.clone()
            action.target = action.source
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': 0,
                'target_types': ['self'],
            }],
            'next': set_self,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target or entity
        if isinstance(target, list):
            target = target[0] if target else entity
        return [{
            'type': 'detect_magic',
            'source': entity,
            'target': target,
            'spell': self.properties,
            'effect': self,
            'range_ft': self.properties.get('range', DETECT_MAGIC_RANGE_FT),
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'detect_magic':
            return None

        source = item.get('source')
        target = item.get('target') or source
        effect = item.get('effect')
        spell = item.get('spell') or {}

        if session is None:
            if battle:
                session = battle.session
            elif source:
                session = source.session

        duration = int(spell.get('duration_seconds') or 600)
        status = 'detect_magic'

        if target and hasattr(target, 'statuses') and status not in target.statuses:
            target.statuses.append(status)

        if source:
            source.add_casted_effect({
                'target': target,
                'effect': effect,
                'expiration': session.game_time + duration if session else None,
            })
            if source.current_concentration() != effect:
                source.concentration_on(effect)

        if target:
            target.register_effect(status, DetectMagicSpell, effect=effect, source=source, duration=duration)

        if session and session.event_manager:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': source,
                'target': target,
            })
            session.event_manager.received_event({
                'event': 'detect_magic',
                'source': source,
                'target': target,
                'range_ft': item.get('range_ft', DETECT_MAGIC_RANGE_FT),
            })

        return target
