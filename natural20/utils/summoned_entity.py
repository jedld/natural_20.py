"""Phase 4 SummonedEntity helper.

A thin wrapper that pairs a loaded NPC/Object with metadata about who
summoned it, when it expires, and what to do when the owner dies. It does
NOT implement a new turn loop — Spiritual Weapon stays bonus-action
commanded; Find Familiar / Conjure-style spells can opt in for cleanup
and serialization.

Usage::

    from natural20.utils.summoned_entity import SummonedEntity

    summon = SummonedEntity(
        entity=loaded_npc,
        owner=caster,
        expiration_round=battle.current_round() + 10,
        on_owner_death='dismiss',
    )
    battle.register_summon(summon)

``Battle`` exposes ``summons_by_owner``, ``register_summon``,
``unregister_summon``, ``summons_for(owner)``, and ``tick_summons()`` which
prunes expired entries on round transitions.
"""

from __future__ import annotations


class SummonedEntity:
    """Lightweight bookkeeping wrapper around a loaded summon entity."""

    def __init__(self, *, entity, owner, expiration_round=None,
                 expiration_time=None, on_owner_death='dismiss',
                 source_id=None, concentration=False):
        self.entity = entity
        self.owner = owner
        self.expiration_round = expiration_round
        self.expiration_time = expiration_time
        self.on_owner_death = on_owner_death  # 'dismiss' | 'persist' | 'wild'
        self.source_id = source_id  # spell or feature id
        self.concentration = bool(concentration)
        self._dismissed = False

    @property
    def entity_uid(self):
        return getattr(self.entity, 'entity_uid', None)

    @property
    def owner_uid(self):
        return getattr(self.owner, 'entity_uid', None)

    def is_expired(self, battle=None) -> bool:
        if self._dismissed:
            return True
        if battle is not None and self.expiration_round is not None:
            if battle.current_round() > self.expiration_round:
                return True
        owner = self.owner
        if owner is not None:
            session = getattr(owner, 'session', None)
            if (session is not None and self.expiration_time is not None
                    and getattr(session, 'game_time', 0) > self.expiration_time):
                return True
            if self.on_owner_death == 'dismiss':
                if getattr(owner, 'dead', None) and callable(owner.dead) and owner.dead():
                    return True
                if getattr(owner, 'unconscious', None) and callable(owner.unconscious):
                    try:
                        if self.concentration and owner.unconscious():
                            return True
                    except Exception:
                        pass
        return False

    def dismiss(self):
        self._dismissed = True

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            'entity_uid': str(self.entity_uid) if self.entity_uid is not None else None,
            'owner_uid': str(self.owner_uid) if self.owner_uid is not None else None,
            'expiration_round': self.expiration_round,
            'expiration_time': self.expiration_time,
            'on_owner_death': self.on_owner_death,
            'source_id': self.source_id,
            'concentration': self.concentration,
            'dismissed': self._dismissed,
        }

    @staticmethod
    def from_dict(data: dict, session) -> 'SummonedEntity':
        registry = getattr(session, 'entity_registry', None)
        ent = registry.get(data['entity_uid']) if (registry and data.get('entity_uid')) else None
        owner = registry.get(data['owner_uid']) if (registry and data.get('owner_uid')) else None
        s = SummonedEntity(
            entity=ent,
            owner=owner,
            expiration_round=data.get('expiration_round'),
            expiration_time=data.get('expiration_time'),
            on_owner_death=data.get('on_owner_death', 'dismiss'),
            source_id=data.get('source_id'),
            concentration=bool(data.get('concentration', False)),
        )
        if data.get('dismissed'):
            s._dismissed = True
        return s

    def __repr__(self):
        return (f"SummonedEntity(entity={getattr(self.entity, 'name', None)!r}, "
                f"owner={getattr(self.owner, 'name', None)!r}, "
                f"expires_round={self.expiration_round})")
