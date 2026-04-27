from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.save_for_half import SaveForHalfMixin


class ThunderwaveSpell(DamageScalingMixin, SaveForHalfMixin, Spell):
    def build_map(self, orig_action):
        def set_target(target=None):
            action = orig_action.clone()
            # Allow None for backward compatibility (tests/builders without UI)
            if target is not None:
                action.target = target
            return action

        # Thunderwave requires choosing a direction for a 15-ft cube originating from you
        return {
            'param': [
                {
                    'type': 'select_cube',
                    'num': 1,
                    'range': self.properties.get('range_cube', 15),
                    'require_los': False
                }
            ],
            'next': set_target
        }

    def _damage(self, battle, crit=False, opts=None):
        # 5e: 2d8 base, +1d8 per slot level above 1st.
        return self._scaled_damage_roll(
            battle, "2d8", "1d8",
            opts=opts, crit=crit,
            description=self.t('dice_roll.spells.generic_damage',
                               spell=self.t('spell.thunderwave')),
        )

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts=opts).expected()

    def _cube_squares_from_face(self, battle_map, origin, towards, size_squares=3):
        """
        Compute a size_squares x size_squares cube whose nearest face is adjacent to the origin
        and oriented toward the 'towards' position. Excludes the origin square.
        """
        ox, oy = origin
        tx, ty = towards
        dx = tx - ox
        dy = ty - oy

        # Choose primary cardinal facing based on larger magnitude
        if abs(dx) >= abs(dy):
            facing = 'E' if dx > 0 else 'W'
        else:
            facing = 'S' if dy > 0 else 'N'

        squares = []
        w, h = battle_map.size
        half = size_squares // 2

        if facing == 'N':
            x_min, x_max = ox - half, ox + half
            y_min, y_max = oy - size_squares, oy - 1
        elif facing == 'S':
            x_min, x_max = ox - half, ox + half
            y_min, y_max = oy + 1, oy + size_squares
        elif facing == 'E':
            x_min, x_max = ox + 1, ox + size_squares
            y_min, y_max = oy - half, oy + half
        else:  # 'W'
            x_min, x_max = ox - size_squares, ox - 1
            y_min, y_max = oy - half, oy + half

        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                if 0 <= x < w and 0 <= y < h:
                    if not (x == ox and y == oy):
                        squares.append((x, y))
        return squares

    def compute_hit_probability(self, battle, opts=None):
        # Approximate with a single target in front if any; otherwise 0.5 by default
        return 0.5

    def resolve(self, entity, battle, spell_action, battle_map):
        src_pos = battle_map.position_of(entity)
        # Determine direction from selected target to orient the cube
        target_pos = spell_action.target if isinstance(spell_action.target, list) else None
        if not target_pos:
            # Fallback: default to facing east if not provided
            target_pos = [src_pos[0] + 1, src_pos[1]]
        # Gather targets in a 15-ft cube originating from the caster (3x3) in the chosen direction
        squares = self._cube_squares_from_face(battle_map, src_pos, target_pos, size_squares=3)
        entity_targets = []
        for (x, y) in squares:
            tgt = battle_map.entity_at(x, y)
            if tgt is not None and tgt != entity:
                if tgt not in entity_targets:
                    entity_targets.append(tgt)
        damage_roll = self._damage(battle, opts={'at_level': spell_action.at_level or 1})
        # Caster's spell save DC; INT-based to stay consistent with other
        # wizard spells in this codebase.
        dc = entity.spell_save_dc('intelligence')

        def push_on_failure(target, _dmg):
            push_to = target.push_from(battle_map, src_pos[0], src_pos[1], distance=10)
            return [{
                'type': 'thunderwave_push',
                'source': entity,
                'target': target,
                'refresh_map': True,
                'map': battle_map,
                'push_to': push_to,
            }]

        return self.resolve_save_for_half(
            entity_targets,
            ability='constitution',
            dc=dc,
            damage_roll=damage_roll,
            attack_name='thunderwave',
            damage_type=self.properties.get('damage_type', 'thunder'),
            battle=battle,
            on_failure=push_on_failure,
        )

    @staticmethod
    def apply(battle, item, session=None):
        # Handle push movement and emit a simple log event
        if item.get('type') == 'thunderwave_push':
            if session is None and battle is not None:
                session = battle.session
            evt_mgr = (battle.event_manager if battle else (session.event_manager if session else None))
            push_to = item.get('push_to')
            if push_to:
                # Move the target
                item['map'].move_to(item['target'], *push_to, battle)
                if evt_mgr:
                    evt_mgr.received_event({
                    'event': 'thunderwave_push',
                    'source': item['source'],
                    'target': item['target'],
                    'position': push_to
                    })
