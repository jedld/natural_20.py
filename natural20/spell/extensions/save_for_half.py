"""SaveForHalfMixin — boilerplate for "Dex save, half on success" spells.

The 5e SRD has dozens of spells that share a single resolve loop:

    for each target in area:
        if it's incapacitated: it auto-fails;
        else it rolls a save;
        on failure → full damage; on success → half damage.

This mixin condenses the loop into one call::

    results.extend(self.resolve_save_for_half(
        targets, ability='dexterity', dc=dc,
        damage_roll=damage_roll,
        attack_name='burning_hands',
        damage_type='fire',
        battle=battle,
    ))

The emitted event dicts are intentionally identical in shape to those
already produced by hand-rolled spells (``BurningHandsSpell``,
``ThunderwaveSpell``) so refactors are drop-in.
"""

from natural20.spell.extensions.save_check import SaveCheck

__all__ = ["SaveForHalfMixin"]


class SaveForHalfMixin:
    """Mixin building the standard ``spell_damage`` event list."""

    def resolve_save_for_half(self, targets, *, ability: str, dc: int,
                              damage_roll, attack_name: str,
                              damage_type: str, battle,
                              opts=None,
                              on_failure=None,
                              on_success=None):
        """Roll saves for every entity in ``targets`` and build events.

        ``damage_roll`` may be either a :class:`DieRoll` (rolled once and
        shared across targets) or a callable receiving the target and
        returning a fresh :class:`DieRoll` per creature — useful for
        spells that re-roll damage per target.

        ``on_failure`` / ``on_success`` are optional callables receiving
        ``(target, damage_value)`` and may return an iterable of extra
        event dicts (e.g. Thunderwave's push) appended after each
        target's damage event.
        """
        if opts is None:
            opts = {}
        save_opts = dict(opts)
        save_opts.setdefault('is_magical', True)

        results = []
        source = getattr(self, 'source', None)
        spell_props = getattr(self, 'properties', {})
        roll_factory = damage_roll if callable(damage_roll) else None

        for target in targets:
            save = SaveCheck.make(target, ability, dc, battle, save_opts,
                                  auto_fail_if_unconscious=True)
            failed = not save.passed

            this_roll = roll_factory(target) if roll_factory else damage_roll
            if ability == 'dexterity' and target.class_feature('evasion'):
                damage_value = this_roll.half() if failed else 0
            else:
                damage_value = this_roll if failed else this_roll.half()

            event = {
                'source': source,
                'target': target,
                'attack_name': attack_name,
                'damage_type': damage_type,
                'attack_roll': None,
                'damage_roll': this_roll,
                'advantage_mod': None,
                'adv_info': None,
                'damage': damage_value,
                'spell_save': save.roll,
                'save_failed': failed,
                'dc': dc,
                'cover_ac': None,
                'type': 'spell_damage',
                'spell': spell_props,
            }
            results.append(event)

            extra = None
            if failed and on_failure is not None:
                extra = on_failure(target, damage_value)
            elif (not failed) and on_success is not None:
                extra = on_success(target, damage_value)
            if extra:
                results.extend(extra)

        return results
