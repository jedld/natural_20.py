"""Hail of Thorns — 1st-level ranger conjuration (SRD 5.2; 2014 PHB timing via YAML).

Delivered by a ranged weapon hit (``natural20/spell/extensions/weapon_hit_spell.py``).
The target and every other creature within 5 feet of it make a Dexterity
save, taking ``damage_dice`` piercing damage (+``damage_dice_per_slot`` per
slot level above 1st) on a failure, half on a success.

* 2024 (``timing: after_hit``): Bonus Action right after the hit, 2d10.
* 2014 (``timing: next_hit``): concentration until the next ranged hit, 1d10.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.extensions.save_for_half import SaveForHalfMixin
from natural20.spell.extensions.weapon_hit_spell import WeaponHitSpell


class HailOfThornsSpell(SaveForHalfMixin, WeaponHitSpell):
    SLUG = 'hail_of_thorns'
    RADIUS_FT = 5

    def damage_formula(self, slot_level):
        base_level = int(self.properties.get('level') or 1)
        base = str(self.properties.get('damage_dice') or '1d10')
        per_slot = str(self.properties.get('damage_dice_per_slot') or '1d10')
        count, _, die = base.partition('d')
        per_count, _, _per_die = per_slot.partition('d')
        extra = max(0, int(slot_level or base_level) - base_level) * int(per_count or 1)
        return f"{int(count or 1) + extra}d{die}"

    def creatures_hit(self, target, battle):
        battle_map = battle.map_for(target) if battle is not None else None
        creatures = [target]
        if battle_map is None:
            return creatures
        reach = self.RADIUS_FT / battle_map.feet_per_grid
        for other in list(battle_map.entities.keys()):
            if other is target or other in creatures:
                continue
            if not hasattr(other, 'save_throw') or getattr(other, 'object', lambda: False)():
                continue
            if other.dead():
                continue
            try:
                if battle_map.distance(target, other) <= reach:
                    creatures.append(other)
            except Exception:
                continue
        return creatures

    def on_weapon_hit(self, caster, target, hit_result, slot_level, battle):
        attack_roll = hit_result.get('attack_roll')
        formula = self.damage_formula(slot_level)
        roll = DieRoll.roll(formula, battle=battle, entity=caster,
                            description='dice_roll.spells.hail_of_thorns')
        dc = self.save_dc(caster)
        items = self.resolve_save_for_half(
            self.creatures_hit(target, battle), ability='dexterity', dc=dc,
            damage_roll=roll, attack_name=self.properties.get('name', 'Hail of Thorns'),
            damage_type=self.properties.get('damage_type', 'piercing'), battle=battle,
            opts={'dc': dc},
        )
        for item in items:
            item['source'] = caster
            item['trigger'] = self.SLUG
            item['cast_level'] = slot_level
            item['triggering_attack_roll'] = attack_roll
        return items
