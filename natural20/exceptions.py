"""Shared base for control-flow exceptions.

These exceptions are raised to *steer* resolution (pause for a player
reaction, yield to a human controller, prompt for Bardic Inspiration)
rather than to report an error. They must propagate out of ``Entity``
event hooks (``resolve_trigger``) and the battle loop; generic
``except Exception`` guards around hooks and the game loop must
re-raise subclasses of :class:`GameLoopControl` so that the
coordinating layer (``webapp`` async-reaction handling) still sees
them.
"""


class GameLoopControl(Exception):
    """Base class for exceptions that pause or redirect the game loop."""
