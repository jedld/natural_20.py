from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from natural20.action import Action
from natural20.die_roll import DieRoll


class BreathWeaponAction(Action):
    """Dragonborn Breath Weapon racial trait action.
    
    Supports cone and line AoE shapes with proper map targeting.
    Uses spell save DC formula: 8 + proficiency bonus + ability modifier.
    """

    # Damage dice by character level per 5e SRD
    DAMAGE_TABLE = {
        1: "2d6",
        3: "3d6",
        5: "4d6",
        7: "5d6",
        9: "6d6",
        11: "7d6",
        13: "8d6",
        15: "9d6",
        17: "10d6",
    }

    # Default range in feet for each shape type
    DEFAULT_RANGES = {
        'cone': 15,      # 15-foot cone
        'line': 15,      # 15-foot line (15x5)
    }

    def __init__(
        self,
        session,
        source,
        target,
        ancestry: str,
        damage_type: str,
        save_ability: str,
        shape: str,
        level: int,
        range_feet: Optional[int] = None,
    ) -> None:
        super().__init__(session, source, 'breath_weapon')
        self.target = target
        self.ancestry = ancestry
        self.damage_type = damage_type
        self.save_ability = save_ability
        self.shape = shape
        self.level = level
        self.range_feet = range_feet or self.DEFAULT_RANGES.get(shape, 15)
        # Breath weapon uses an Action, not a bonus action
        self.as_bonus_action = False

    def label(self) -> str:
        return f"Breath Weapon ({self.ancestry.title()})"

    def button_label(self) -> Optional[str]:
        return self.label()

    def name(self) -> str:
        return self.label()

    def _damage_dice(self) -> str:
        """Calculate damage dice based on character level."""
        level = self.level
        # Find the highest level threshold that our character level meets
        for threshold in sorted(self.DAMAGE_TABLE.keys(), reverse=True):
            if level >= threshold:
                return self.DAMAGE_TABLE[threshold]
        return "2d6"  # Default for level 1

    def compute_hit_probability(self, battle, opts=None):
        """Breath weapon requires a saving throw, not a hit roll."""
        return 1.0

    def avg_damage(self, battle, opts=None):
        """Average damage assuming half targets fail save."""
        dice_str = self._damage_dice()
        num_dice = int(dice_str.replace('d6', ''))
        return num_dice * 3.5  # Average of d6 is 3.5

    def _get_save_dc(self) -> int:
        """Calculate spell save DC using proper formula.
        
        Formula: 8 + proficiency bonus + ability modifier
        """
        save_ability = self.save_ability
        
        # Try to use entity's spell_save_dc method if available
        if hasattr(self.source, 'spell_save_dc'):
            return self.source.spell_save_dc(save_ability)
        
        # Fallback: calculate manually
        proficiency_bonus = getattr(self.source, 'proficiency_bonus', 2)
        ability_mod = self.source.ability_modifier(save_ability)
        return 8 + proficiency_bonus + ability_mod

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        battle = opts.get('battle')

        # Get saving throw DC using proper formula
        dc = self._get_save_dc()

        # Roll damage
        dice_str = self._damage_dice()
        damage_roll = DieRoll.roll(
            dice_str,
            battle=battle,
            entity=self.source,
            description=f'Breath Weapon ({self.ancestry})'
        )

        # Determine targets based on shape
        targets = self._get_targets(map, battle)

        results = []
        for target in targets:
            # Target makes saving throw
            save_result = target.saving_throw(self.save_ability, battle=battle)
            
            if save_result and save_result.total >= dc:
                # Success - half damage
                half_damage = damage_roll.result() // 2
                results.append({
                    'type': 'breath_weapon_damage',
                    'source': self.source,
                    'target': target,
                    'damage_type': self.damage_type,
                    'damage_roll': half_damage,
                    'damage': half_damage,
                    'save_success': True,
                    'ancestry': self.ancestry,
                })
            else:
                # Failure - full damage
                results.append({
                    'type': 'breath_weapon_damage',
                    'source': self.source,
                    'target': target,
                    'damage_type': self.damage_type,
                    'damage_roll': damage_roll,
                    'damage': damage_roll,
                    'save_success': False,
                    'ancestry': self.ancestry,
                })

        self.result = results
        
        # Emit battle event
        if session and hasattr(session, 'event_manager'):
            session.event_manager.received_event({
                'event': 'breath_weapon_used',
                'source': self.source,
                'targets': targets,
                'ancestry': self.ancestry,
                'damage_type': self.damage_type,
                'shape': self.shape,
                'dc': dc,
            })
        
        return self

    def _get_targets(self, map, battle) -> List:
        """Get targets based on breath weapon shape.
        
        Uses Map.squares_in_cone() for cone shapes and
        Map.squares_in_line() for line shapes.
        """
        if not map or not battle:
            # Fallback to single target if map/battle unavailable
            if self.target:
                return [self.target] if not isinstance(self.target, list) else self.target
            return []
        
        # Get caster position
        caster_pos = map.position_of(self.source)
        if not caster_pos:
            return []
        
        # Get target squares based on shape
        squares = self._get_aoe_squares(map, caster_pos)
        
        if not squares:
            return []
        
        # Collect entities at those squares
        targets = []
        for sq in squares:
            entity = map.entity_at(sq[0], sq[1])
            if entity and entity != self.source:
                if entity not in targets:
                    targets.append(entity)
        
        return targets

    def _get_aoe_squares(self, map, caster_pos: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Get affected squares based on shape and targeting."""
        range_squares = max(1, self.range_feet // map.feet_per_grid)
        
        # If we have a specific target coordinate, use it
        if isinstance(self.target, (list, tuple)) and len(self.target) >= 2:
            target_pos = (int(self.target[0]), int(self.target[1]))
        elif hasattr(self.target, 'entity_uid'):
            # Target is an entity, get its position
            target_pos = map.position_of(self.target)
            if not target_pos:
                return []
        else:
            # Default: use direction from caster toward center of map or first enemy
            target_pos = self._determine_default_direction(map, caster_pos)
        
        if not target_pos:
            return []
        
        # Get squares based on shape
        if self.shape == 'cone':
            return map.squares_in_cone(
                caster_pos, target_pos, range_squares, require_los=False
            )
        elif self.shape == 'line':
            return map.squares_in_line(
                caster_pos, target_pos,
                length_ft=self.range_feet,
                width_ft=5,
                require_los=False,
            )
        else:
            # Unknown shape, fallback to cone
            return map.squares_in_cone(
                caster_pos, target_pos, range_squares, require_los=False
            )
    
    def _determine_default_direction(self, map, caster_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Determine default direction for AoE when no target specified."""
        # Try to find nearest enemy
        if hasattr(self, 'session') and self.session:
            battle = self.session.current_battle
            if battle:
                for entity in battle.entities:
                    if entity != self.source and not entity.is_ally(self.source):
                        pos = map.position_of(entity)
                        if pos:
                            return pos
        
        # Fallback: direction toward map center
        map_w, map_h = map.size
        return (map_w // 2, map_h // 2)

    def build_map(self):
        """Build targeting map for breath weapon.
        
        Returns select_cone for cone shapes, select_line for line shapes.
        """
        base_map = {
            'range': self.range_feet,
            'shape': self.shape,
            'damage_type': self.damage_type,
        }
        
        if self.shape == 'cone':
            return {
                'type': 'select_cone',
                **base_map,
            }
        elif self.shape == 'line':
            return {
                'type': 'select_line',
                **base_map,
            }
        else:
            # Fallback to cone
            return {
                'type': 'select_cone',
                **base_map,
            }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize action to dictionary."""
        return {
            'action_type': self.action_type,
            'source': self.source.entity_uid if self.source else None,
            'target': self.target.entity_uid if hasattr(self.target, 'entity_uid') else self.target,
            'ancestry': self.ancestry,
            'damage_type': self.damage_type,
            'save_ability': self.save_ability,
            'shape': self.shape,
            'level': self.level,
            'range_feet': self.range_feet,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any], session) -> 'BreathWeaponAction':
        """Deserialize action from dictionary."""
        source = session.entity_by_uid(data.get('source')) if data.get('source') else None
        target_uid = data.get('target')
        target = None
        if target_uid and isinstance(target_uid, str):
            target = session.entity_by_uid(target_uid)
        elif target_uid:
            target = target_uid
        
        return BreathWeaponAction(
            session=session,
            source=source,
            target=target,
            ancestry=data.get('ancestry', 'dragonborn'),
            damage_type=data.get('damage_type', 'fire'),
            save_ability=data.get('save_ability', 'constitution'),
            shape=data.get('shape', 'cone'),
            level=data.get('level', 1),
            range_feet=data.get('range_feet'),
        )
