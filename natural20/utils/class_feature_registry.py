"""Phase 4 ClassFeatureAction registry.

Class features that grant Action objects (Action Surge, Channel Divinity
variants, Bardic Inspiration, Lay on Hands, etc.) currently appear as
hardcoded ``elif action_type == FooAction`` branches inside
``PlayerCharacter.available_actions``. This registry lets new features
declare themselves once and be picked up automatically.

Registration happens at import time::

    from natural20.utils.class_feature_registry import register_class_feature

    @register_class_feature(
        feature_id='channel_divinity_turn_undead',
        action_class=TurnUndeadAction,
        provides=lambda entity: entity.class_feature('channel_divinity'),
    )
    class TurnUndeadAction(...):
        ...

Lookup is read-only — existing branches keep working untouched.
"""

from __future__ import annotations

from typing import Callable, List


_REGISTRY: dict = {}


def register_class_feature(*, feature_id, action_class, provides=None,
                           builder=None):
    """Register a class feature provider.

    ``feature_id``: short string id, used as the action's ``action_type``.
    ``action_class``: the Action subclass to instantiate.
    ``provides``: optional ``(entity) -> bool`` predicate; defaults to
        ``action_class.can(entity, None)``.
    ``builder``: optional ``(session, entity, feature_id) -> Action``;
        defaults to ``action_class(session, entity, feature_id)``.
    """
    def _register(cls):
        _REGISTRY[str(feature_id)] = {
            'action_class': cls,
            'provides': provides,
            'builder': builder,
        }
        return cls
    # Allow either decorator usage or direct call with the class supplied.
    if action_class is not None:
        _register(action_class)
        return action_class
    return _register


def unregister_class_feature(feature_id) -> bool:
    return _REGISTRY.pop(str(feature_id), None) is not None


def registered_features() -> List[str]:
    return sorted(_REGISTRY.keys())


def collect_class_feature_actions(session, entity, battle=None) -> list:
    """Return Action instances for every registered feature this entity has."""
    out = []
    for feature_id, spec in _REGISTRY.items():
        provides: Callable = spec.get('provides')
        action_class = spec['action_class']
        try:
            available = (
                provides(entity) if callable(provides)
                else getattr(action_class, 'can', lambda *a, **k: False)(entity, battle)
            )
        except Exception:
            available = False
        if not available:
            continue
        builder = spec.get('builder')
        try:
            action = (
                builder(session, entity, feature_id) if callable(builder)
                else action_class(session, entity, feature_id)
            )
        except Exception:
            continue
        out.append(action)
    return out
