"""Magical Darkness placeable entity used by the Darkness spell."""
import uuid

from natural20.entity import Entity


class Darkness(Entity):
    """A 15-foot-radius sphere of magical darkness placed on the map.

    The object is intentionally minimal: it occupies a single tile (its
    center), is non-blocking and non-targetable, and exposes
    ``dark_properties()`` so the lighting builder can subtract illumination
    in its area of effect.
    """

    def __init__(self, session, owner, radius_feet=15, **kwargs):
        super().__init__(name='magical_darkness', description='', attributes={})
        self.session = session
        self.owner = owner
        self.group = getattr(owner, 'group', None)
        self.radius_feet = radius_feet
        self.entity_uid = str(uuid.uuid4())
        self.properties = {
            'magical_darkness': True,
            'name': 'Magical Darkness',
            'description': f"A {radius_feet}-foot-radius sphere of magical darkness."
        }

    # ------------------------------------------------------------------ map
    def dark_properties(self):
        return {'radius': self.radius_feet}

    def light_properties(self):
        return None

    def size(self):
        return 'medium'

    def token_size(self):
        return 1

    def token(self):
        return ['☼']

    def token_image(self):
        return 'token_darkness.png'

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
