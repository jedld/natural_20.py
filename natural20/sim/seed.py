"""Process-wide seeding for reproducible headless battles.

Dice in ``natural20.die_roll`` read the global ``random`` module. Entity,
action, and tile ids are ``uuid4`` values minted at load time; those ids
change set iteration order, so a seeded ``random`` is not enough on its own.
"""

from __future__ import annotations

import random
import uuid


def pin_uuid4(seed: int) -> None:
    """Replace ``uuid.uuid4`` with a generator fixed by ``seed``.

    Uids are opaque labels. The stand-in is safe for a simulation process
    and must not be used in a long-running server that shares this interpreter
    with other work.
    """
    rng = random.Random(f"n20-sim-uuid-{seed}")

    def _uuid4():
        return uuid.UUID(int=rng.getrandbits(128), version=4)

    uuid.uuid4 = _uuid4


def seed_process(seed: int) -> None:
    """Seed global dice and pin ``uuid4`` for one trial."""
    random.seed(int(seed))
    pin_uuid4(int(seed))
