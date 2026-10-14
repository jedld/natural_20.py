"""Magical Darkness placeable entity used by the Darkness spell."""
from natural20.spell.objects.spell_area_source import SpellAreaSource


class Darkness(SpellAreaSource):
    """A sphere of magical darkness placed on the map.

    The object is intentionally minimal: it occupies a single tile (its
    center), is non-blocking and non-targetable, and exposes
    ``dark_properties()`` so the lighting builder can subtract illumination
    in its area of effect. ``spell_level`` is the slot level of the spell
    that created it (Daylight dispels darkness from spells of level 3 or
    lower).
    """

    OBJECT_NAME = 'magical_darkness'
    LABEL = 'Magical Darkness'
    TOKEN = '☼'
    TOKEN_IMAGE = 'token_darkness.png'

    def __init__(self, session, owner, radius_feet=15, spell_level=None, entity_uid=None, **kwargs):
        super().__init__(session, owner, radius_feet, spell_level=spell_level, entity_uid=entity_uid)
        self.properties['magical_darkness'] = True

    def description_text(self):
        return f"A {self.radius_feet}-foot-radius sphere of magical darkness."

    def dark_properties(self):
        return {'radius': self.radius_feet}
