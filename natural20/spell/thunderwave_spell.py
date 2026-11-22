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

    def _damage(self, battle, crit=False, opts=None, estimated=False):
        # 5e: 2d8 base, +1d8 per slot level above 1st.
        return self._scaled_damage_roll(
            battle, "2d8", "1d8",
            opts=opts, crit=crit,
            description=self.t('dice_roll.spells.generic_damage',
                               spell=self.t('spell.thunderwave')),
            estimated=estimated,
        )

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts=opts, estimated=True).expected()

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
            # Corpses take no saves, damage or push from area spells.
            if tgt is not None and tgt != entity and not getattr(tgt, 'dead', lambda: False)():
                # Areas of effect need line of effect: a creature behind a
                # wall (total cover from the origin) is not in the cube
                # (SRD "Areas of Effect", issue #6 item 59). The cube
                # resolver predates the sphere fix from item 19.
                try:
                    if battle_map.line_of_sight(src_pos[0], src_pos[1], x, y,
                                                inclusive=True) is None:
                        continue
                except Exception:
                    pass
                if tgt not in entity_targets:
                    entity_targets.append(tgt)
        damage_roll = self._damage(battle, opts={'at_level': spell_action.at_level or 1})
        # Caster's spell save DC; INT-based to stay consistent with other
        # wizard spells in this codebase.
        dc = entity.spell_save_dc('intelligence')

        def push_on_failure(target, _dmg):
            # The landing square is computed at commit time (see apply) so
            # that earlier pushes are already applied and no two pushed
            # creatures can land on (and overwrite) one square.
            return [{
                'type': 'thunderwave_push',
                'source': entity,
                'target': target,
                'refresh_map': True,
                'map': battle_map,
                'push_from': [int(src_pos[0]), int(src_pos[1])],
                'distance': 10,
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
            if push_to is None and item.get('push_from') is not None:
                # Recompute the landing square now, at commit time, so each
                # push sees the squares freed/occupied by the pushes applied
                # before it and no two creatures land on one square.
                push_to = item['target'].push_from(
                    item['map'], item['push_from'][0], item['push_from'][1],
                    distance=item.get('distance', 10))
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
