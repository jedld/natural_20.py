"""Thunder Step — teleport plus a thunderclap where the caster stood.

Reuses Misty Step's targeting and teleport. Before the caster vanishes,
every other creature within ``departure_radius`` (10 ft) of the departure
square makes a ``departure_save`` (Constitution) save, taking
``departure_damage`` (3d10 thunder, +``departure_damage_per_slot`` per slot
level above the spell's) or half on a success. Bringing a willing passenger
along is not modelled.
"""
from __future__ import annotations

from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.save_for_half import SaveForHalfMixin
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.misty_step_spell import MistyStepSpell


class ThunderStepSpell(DamageScalingMixin, SaveForHalfMixin, MistyStepSpell):
    SPELL_ID = 'thunder_step'

    def resolve(self, entity, battle, spell_action, battle_map):
        teleport = super().resolve(entity, battle, spell_action, battle_map)
        if not teleport or battle_map is None:
            return teleport
        origin = teleport[0].get('from')
        if not origin:
            return teleport
        radius = int(self.properties.get('departure_radius', 10))
        targets = []
        for x, y in battle_map.squares_in_radius((int(origin[0]), int(origin[1])), radius, require_los=False):
            for creature in battle_map.entities_at(x, y):
                if (creature is not entity and creature not in targets
                        and not creature.object() and hasattr(creature, 'take_damage')):
                    targets.append(creature)
        base_level = int(self.properties.get('level', 3))
        at_level = getattr(spell_action, 'at_level', None) or base_level
        damage = self.resolve_save_for_half(
            targets,
            ability=self.properties.get('departure_save', 'constitution'),
            dc=entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action)),
            damage_roll=lambda _t: self._scaled_damage_roll(
                battle, self.properties.get('departure_damage', '3d10'),
                self.properties.get('departure_damage_per_slot', '1d10'),
                opts={'at_level': at_level}, base_level=base_level,
                description='dice_roll.spells.thunder_step'),
            attack_name='thunder_step',
            damage_type=self.properties.get('damage_type', 'thunder'),
            battle=battle,
        )
        return damage + teleport
