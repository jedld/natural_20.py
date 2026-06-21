from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.weapons import damage_modifier
from natural20.utils.ac_utils import effective_ac
from natural20.spell.extensions.hit_computations import AttackSpell


class GreenFlameBladeSpell(AttackSpell):
    """Green-Flame Blade: melee spell attack that hits for weapon damage + fire, then splashes fire to a second target."""

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties.get('range', 5),
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }

    def _primary_damage(self, battle, crit=False):
        entity = self.source
        level = 1
        if entity.level() >= 5:
            level += 1
        if entity.level() >= 11:
            level += 1
        if entity.level() >= 17:
            level += 1
        return DieRoll.roll(f"1d8 + {level}", crit=crit, battle=battle, entity=entity,
                            description=self.t('dice_roll.spells.green_flame_blade'))

    def _splash_damage(self, battle, crit=False):
        entity = self.source
        level = 1
        if entity.level() >= 5:
            level += 1
        if entity.level() >= 11:
            level += 1
        if entity.level() >= 17:
            level += 1
        return DieRoll.roll(f"1d8", crit=crit, battle=battle, entity=entity,
                            description=self.t('dice_roll.spells.green_flame_blade_splash'))

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if not target:
            return [{
                "type": "spell_miss",
                "source": entity,
                "target": entity,
                "attack_name": "green_flame_blade",
                "damage_type": "fire",
                "attack_roll": None,
                "damage_roll": None,
                "advantage_mod": 0,
                "adv_info": "",
                "cover_ac": [],
                "spell": self.properties
            }]

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = evaluate_spell_attack(
            self.session, entity, target, self.properties, battle=battle, opts={"action": spell_action})

        result = list(events)

        if hit:
            primary_damage = self._primary_damage(battle, crit=attack_roll.nat_20())
            result.extend([{
                "source": entity,
                "target": target,
                "attack_name": "green_flame_blade",
                "damage_type": "fire",
                "attack_roll": attack_roll,
                "damage_roll": primary_damage,
                "advantage_mod": advantage_mod,
                "adv_info": adv_info,
                "damage": primary_damage,
                "cover_ac": cover_ac_adjustments,
                "type": "spell_damage",
                "spell": self.properties
            }])

            # Find a second target within 5 feet of the first target
            second_target = None
            if battle_map:
                tx, ty = target.map_coords()
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = tx + dx, ty + dy
                        for e in battle_map.entities_at(nx, ny):
                            if e is not entity and e is not target and e not in [r.get('target') for r in result]:
                                second_target = e
                                break
                        if second_target:
                            break
                    if second_target:
                        break

            if second_target:
                splash_damage = self._splash_damage(battle)
                result.extend([{
                    "source": entity,
                    "target": second_target,
                    "attack_name": "green_flame_blade_splash",
                    "damage_type": "fire",
                    "attack_roll": None,
                    "damage_roll": splash_damage,
                    "advantage_mod": 0,
                    "adv_info": "",
                    "damage": splash_damage,
                    "cover_ac": [],
                    "type": "spell_damage",
                    "spell": self.properties
                }])

        else:
            result.extend([{
                "type": "spell_miss",
                "source": entity,
                "target": target,
                "attack_name": "green_flame_blade",
                "damage_type": "fire",
                "attack_roll": attack_roll,
                "damage_roll": None,
                "advantage_mod": advantage_mod,
                "adv_info": adv_info,
                "cover_ac": cover_ac_adjustments,
                "spell": self.properties
            }])

        return result
