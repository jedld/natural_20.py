"""Wind Walk (SRD) — 6th-level transmutation, mist form.

You and up to ten willing creatures within 30 feet take gaseous form for up to
8 hours (no concentration). Reuses the Gaseous Form mist machinery
(``natural20/spell/gaseous_form_spell.py``) with a 300-foot fly speed.
Casting time (1 minute) already blocks use during battle.
"""
from __future__ import annotations

from natural20.spell.gaseous_form_spell import EFFECT_TYPES, GaseousFormEffect
from natural20.spell.spell import Spell

WIND_WALK_SPEED = 300


class WindWalkMistEffect(GaseousFormEffect):
    """Gaseous Form effect raised to the Wind Walk fly speed."""

    def __init__(self, source, target, added_status=True, granted_flight=False,
                 speed=WIND_WALK_SPEED):
        super().__init__(source, target, added_status=added_status,
                         granted_flight=granted_flight)
        self.speed = int(speed or WIND_WALK_SPEED)

    def label(self):
        return 'Mist Form (Wind Walk)'

    @staticmethod
    def fly_speed(entity, opt=None):
        return int(getattr((opt or {}).get('effect'), 'speed', WIND_WALK_SPEED))

    @staticmethod
    def speed_override(entity, opt=None):
        return int(getattr((opt or {}).get('effect'), 'speed', WIND_WALK_SPEED))

    def apply_to(self, target, duration):
        for effect_type in EFFECT_TYPES:
            target.register_effect(effect_type, type(self), effect=self,
                                   source=self.source, duration=duration)


class WindWalkSpell(Spell):

    def build_map(self, orig_action):
        def set_targets(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': int(self.properties.get('max_targets', 10)),
                'range': self.properties.get('range', 30),
                'target_types': ['allies', 'self'],
            }],
            'next': set_targets,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        raw = spell_action.target
        if raw is None:
            targets = [entity]
        elif isinstance(raw, (list, tuple)):
            targets = [t for t in raw if not isinstance(t, (list, tuple))]
        else:
            targets = [raw]
        # SRD: you and up to ten willing creatures — the caster is always included.
        if entity not in targets:
            targets = [entity] + list(targets)
        return [{
            'type': 'wind_walk', 'source': entity, 'target': target,
            'effect': self, 'spell': self.properties,
        } for target in targets]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'wind_walk':
            return None
        source, target = item['source'], item['target']
        if target is None or isinstance(target, (list, tuple)):
            return None
        if session is None:
            session = battle.session if battle is not None else source.session
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 28800))
        speed = int(spell.get('fly_speed', WIND_WALK_SPEED))
        added = 'gaseous_form' not in (getattr(target, 'statuses', None) or [])
        if added:
            target.statuses.append('gaseous_form')
        granted = not (target.properties.get('speed_fly') or 0)
        effect = WindWalkMistEffect(source, target, added_status=added,
                                    granted_flight=granted, speed=speed)
        effect.apply_to(target, duration)
        source.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + duration})
        if granted:
            target._granted_flight = True
        if hasattr(target, 'fly'):
            target.fly()
        # Wind Walk is not concentration.
        session.event_manager.received_event({
            'event': 'wind_walk',
            'source': source,
            'target': target,
        })
        return target
