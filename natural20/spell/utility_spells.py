"""Small SRD utility spells with simple, log-first mechanics.

* Feather Fall — up to five falling creatures within 60 ft get the
  ``feather_fall`` status for 1 minute (``map_stack_descent`` already skips
  fall damage for it).
* Prestidigitation — a harmless sensory trick at a point within 10 ft.
* Mending — repairs a single break or tear in an object within reach.
* Identify — reveals the magic items a touched creature carries and the
  spells currently affecting it.
"""
from __future__ import annotations

import uuid

from natural20.spell.spell import Spell


def _creatures(target):
    if isinstance(target, (list, tuple)):
        return [t for t in target if hasattr(t, 'entity_uid')]
    return [target] if hasattr(target, 'entity_uid') else []


def _point(target):
    if isinstance(target, (list, tuple)) and len(target) == 2 \
            and all(isinstance(v, (int, float)) for v in target):
        return [int(target[0]), int(target[1])]
    return None


class _LogSpell(Spell):
    """Spell whose resolution is a single logged event."""

    EVENT = None


class FeatherFallEffect:
    def __init__(self, source, target, added_status=True):
        self.source = source
        self.target = target
        self.added_status = bool(added_status)
        self.uid = f"feather_fall:{uuid.uuid4().hex[:10]}"
        self.ended = False

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return 'feather_fall'

    def label(self):
        return 'Feather Fall'

    def dismiss(self, entity, _descriptor=None, opts=None):
        if self.ended:
            return
        self.ended = True
        target = self.target
        if target is None:
            return
        if self.added_status and 'feather_fall' in (getattr(target, 'statuses', None) or []):
            target.statuses.remove('feather_fall')
        if target is not entity and hasattr(target, 'remove_effect'):
            target.remove_effect(self)


class FeatherFallSpell(_LogSpell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': int(self.properties.get('max_targets', 5)),
                'range': self.properties.get('range', 60),
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        targets = _creatures(spell_action.target) or [entity]
        return [{
            'type': 'feather_fall',
            'source': entity,
            'target': targets[0],
            'targets': targets[:int(self.properties.get('max_targets', 5))],
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'feather_fall':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        duration = int((item.get('spell') or {}).get('duration_seconds', 60))
        for target in item.get('targets') or []:
            added = 'feather_fall' not in target.statuses
            if added:
                target.statuses.append('feather_fall')
            effect = FeatherFallEffect(source, target, added_status=added)
            source.add_casted_effect({'target': target, 'effect': effect,
                                      'expiration': session.game_time + duration})
            target.register_effect('feather_fall', FeatherFallSpell, effect=effect,
                                   source=source, duration=duration)
        session.event_manager.received_event({
            'event': 'feather_fall',
            'source': source,
            'target': item.get('target'),
            'targets': item.get('targets') or [],
        })
        return item.get('target')


class _PointLogSpell(_LogSpell):
    DEFAULT_RANGE = 10

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_square',
                'num': 1,
                'range': self.properties.get('range', self.DEFAULT_RANGE),
            }],
            'next': set_target,
        }

    def _target_point(self, entity, spell_action, battle_map):
        target = spell_action.target
        point = _point(target)
        if point is None:
            creatures = _creatures(target)
            if creatures and battle_map is not None:
                pos = battle_map.position_of(creatures[0])
                point = [int(pos[0]), int(pos[1])] if pos else None
        if point is None and battle_map is not None:
            pos = battle_map.position_of(entity)
            point = [int(pos[0]), int(pos[1])] if pos else None
        return point

    def resolve(self, entity, battle, spell_action, battle_map):
        point = self._target_point(entity, spell_action, battle_map)
        item = {
            'type': self.EVENT,
            'source': entity,
            'target': point,
            'effect': self,
            'spell': self.properties,
        }
        item.update(self.details(entity, battle_map, point, spell_action))
        return [item]

    def details(self, entity, battle_map, point, spell_action):
        return {}

    @classmethod
    def _log(cls, battle, item, session, extra=None):
        if item.get('type') != cls.EVENT:
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        event = {'event': cls.EVENT, 'source': source, 'target': item.get('target')}
        event.update(extra or {})
        session.event_manager.received_event(event)
        return source


class PrestidigitationSpell(_PointLogSpell):
    EVENT = 'prestidigitation'
    DEFAULT_RANGE = 10
    TRICKS = ('sensory', 'light', 'clean', 'flavor', 'mark', 'illusion')

    def details(self, entity, battle_map, point, spell_action):
        trick = (getattr(spell_action, 'opts', None) or {}).get('trick') or 'sensory'
        return {'trick': trick if trick in self.TRICKS else 'sensory'}

    @staticmethod
    def apply(battle, item, session=None):
        return PrestidigitationSpell._log(battle, item, session, {'trick': item.get('trick')})


class MendingSpell(_PointLogSpell):
    EVENT = 'mending'
    DEFAULT_RANGE = 5

    def details(self, entity, battle_map, point, spell_action):
        repaired = None
        if battle_map is not None and point is not None:
            try:
                objects = battle_map.objects_at(point[0], point[1])
            except Exception:
                objects = []
            for obj in objects or []:
                label = getattr(obj, 'label', None)
                repaired = label() if callable(label) else getattr(obj, 'name', None)
                if repaired:
                    break
        return {'object_name': repaired}

    @staticmethod
    def apply(battle, item, session=None):
        return MendingSpell._log(battle, item, session, {'object_name': item.get('object_name')})


def _is_magic_item(item):
    if not isinstance(item, dict):
        return False
    if item.get('magical') or item.get('magic') or item.get('attunement') \
            or item.get('requires_attunement') or item.get('rarity'):
        return True
    return 'magic' in str(item.get('type', '')).lower()


def magic_items_of(creature):
    session = getattr(creature, 'session', None)
    if session is None:
        return []
    keys = list((getattr(creature, 'properties', None) or {}).get('equipped', []) or [])
    keys += [k for k in (getattr(creature, 'inventory', None) or {}).keys() if k not in keys]
    found = []
    for key in keys:
        try:
            item = session.load_thing(key)
        except Exception:
            continue
        if _is_magic_item(item):
            found.append(item.get('label') or item.get('name') or str(key))
    return found


class IdentifySpell(_LogSpell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 5),
                'target_types': ['allies', 'self', 'enemies'],
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        creatures = _creatures(spell_action.target)
        target = creatures[0] if creatures else entity
        from natural20.utils.dispel import spells_on
        spells = []
        for effect, _caster in spells_on(target, battle):
            label = getattr(effect, 'label', None)
            name = label() if callable(label) else (getattr(effect, 'name', None) or str(effect))
            if name not in spells:
                spells.append(name)
        return [{
            'type': 'identify',
            'source': entity,
            'target': target,
            'items': magic_items_of(target),
            'spells': spells,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'identify':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        session.event_manager.received_event({
            'event': 'identify',
            'source': source,
            'target': item.get('target'),
            'items': list(item.get('items') or []),
            'spells': list(item.get('spells') or []),
        })
        return item.get('target')
