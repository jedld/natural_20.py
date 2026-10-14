"""Daylight sphere placed on the map by the Daylight spell (cast at a point)."""
from natural20.spell.objects.spell_area_source import SpellAreaSource


class DaylightSource(SpellAreaSource):
    """Bright light in ``radius_feet`` plus dim light for ``dim_feet`` more."""

    OBJECT_NAME = 'daylight'
    LABEL = 'Daylight'
    TOKEN = '☀'
    TOKEN_IMAGE = 'token_daylight.png'
    DIM_FEET = 60

    def description_text(self):
        return (f"A {self.radius_feet}-foot-radius sphere of magical daylight "
                f"with dim light {self.DIM_FEET} feet beyond.")

    def light_properties(self):
        return {'bright': self.radius_feet, 'dim': self.DIM_FEET}
