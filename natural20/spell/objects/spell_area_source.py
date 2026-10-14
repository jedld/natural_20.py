"""Base class for inert map entities that mark a spell's area (Darkness, Daylight).

The object sits on one tile (the area's center), is passable, transparent and
untargetable, never takes a turn, and is read by the lighting builder through
``light_properties()`` / ``dark_properties()``.

Save/load: subclasses are listed in ``CLASS_TAG_MAPPING``
(``natural20/utils/serialization.py``) and round-trip through
``to_dict``/``from_dict``. The creating caster is stored by UID and resolved
lazily through the session registry.
"""
from __future__ import annotations

import uuid

from natural20.entity import Entity


class SpellAreaSource(Entity):
    OBJECT_NAME = 'spell_area'
    LABEL = 'Spell Area'
    TOKEN = '*'
    TOKEN_IMAGE = None

    def __init__(self, session, owner, radius_feet, spell_level=None, entity_uid=None):
        super().__init__(name=self.OBJECT_NAME, description='', attributes={})
        self.session = session
        self._owner = None if isinstance(owner, str) else owner
        self._owner_uid = getattr(owner, 'entity_uid', None) if not isinstance(owner, str) else owner
        self.group = getattr(owner, 'group', None)
        self.radius_feet = int(radius_feet)
        self.spell_level = int(spell_level) if spell_level is not None else None
        self.entity_uid = entity_uid or str(uuid.uuid4())
        self.properties = {
            'name': self.LABEL,
            'description': self.description_text(),
        }

    def description_text(self):
        return f"A {self.radius_feet}-foot-radius {self.LABEL.lower()}."

    @property
    def owner(self):
        if self._owner is None and self._owner_uid and self.session is not None:
            self._owner = self.session.entity_by_uid(self._owner_uid)
        return self._owner

    @owner.setter
    def owner(self, value):
        self._owner = value
        self._owner_uid = getattr(value, 'entity_uid', None)

    # ------------------------------------------------------------ save/load
    def to_dict(self):
        return {
            'session': self.session,
            'owner_uid': self._owner_uid,
            'radius_feet': self.radius_feet,
            'spell_level': self.spell_level,
            'entity_uid': self.entity_uid,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data.get('session'),
            data.get('owner_uid'),
            radius_feet=data.get('radius_feet') or 0,
            spell_level=data.get('spell_level'),
            entity_uid=data.get('entity_uid'),
        )

    # ------------------------------------------------------------------ map
    def dark_properties(self):
        return None

    def light_properties(self):
        return None

    def size(self):
        return 'medium'

    def token_size(self):
        return 1

    def token(self):
        return [self.TOKEN]

    def token_image(self):
        return self.TOKEN_IMAGE

    def label(self):
        return self.properties['name']

    # -------------------------------------------------------- battle hooks
    def passable(self, origin=None):
        return True

    def opaque(self, origin=None):
        return False

    def placeable(self, *args, **kwargs):
        return False

    def allow_targeting(self):
        return False

    def npc(self):
        return True

    def passive(self):
        return True

    # ---------------------------------------------------- combat-no-ops
    def hp(self):
        return None

    def max_hp(self):
        return None

    def health_percent(self):
        return 1.0

    def dead(self):
        return False

    def unconscious(self):
        return False

    def has_reaction(self, _battle):
        return False

    def reset_turn(self, battle):  # never takes a turn
        return None
