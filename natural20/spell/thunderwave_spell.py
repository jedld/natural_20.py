from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
import pdb


class ThunderwaveSpell(Spell):
    def build_map(self, orig_action):
        return orig_action

    def _damage(self, battle, crit=False, opts=None):
        if opts is None:
            opts = {}
        at_level = opts.get('at_level', getattr(self.action, 'at_level', 1) or 1)
        dice = 2 + max(0, at_level - 1)  # 2d8 + 1d8 per slot level above 1st
        dice = f"{dice}d8"
        return DieRoll.roll(dice, crit=crit, battle=battle, entity=self.source, description=self.t('dice_roll.spells.generic_damage', spell=self.t('spell.thunderwave')))

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts=opts).expected()

    def _cube_squares_centered(self, battle_map, src, radius=1):
        """
        Compute a 15-ft cube centered on the caster (3x3 area), excluding the caster's own square.
        This approximates "originating from you" without requiring a direction.
        """
        sx, sy = src
        squares = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                x = sx + dx
                y = sy + dy
                if 0 <= x < battle_map.size[0] and 0 <= y < battle_map.size[1]:
                    squares.append((x, y))
        return squares

    def compute_hit_probability(self, battle, opts=None):
        # Approximate with a single target in front if any; otherwise 0.5 by default
        return 0.5

    def resolve(self, entity, battle, spell_action, battle_map):
        results = []
        src_pos = battle_map.position_of(entity)
        # Gather targets in a 15-ft cube centered on the caster (3x3)
        squares = self._cube_squares_centered(battle_map, src_pos, radius=1)
        entity_targets = []
        for (x, y) in squares:
            tgt = battle_map.entity_at(x, y)
            if tgt is not None and tgt != entity:
                if tgt not in entity_targets:
                    entity_targets.append(tgt)
        damage_roll = self._damage(battle, opts={'at_level': spell_action.at_level or 1})
        for tgt in entity_targets:
            failed = False

            if tgt.conscious():
                save = tgt.save_throw('constitution', battle, { 'is_magical': True })
                # Use INT-based DC consistent with other wizard spells in this codebase
                dc = entity.spell_save_dc('intelligence')
                failed = save < dc
            else:
                failed = True
            if failed:
                results.append({
                    'source': entity,
                    'target': tgt,
                    'attack_name': 'thunderwave',
                    'damage_type': self.properties.get('damage_type', 'thunder'),
                    'attack_roll': None,
                    'damage_roll': damage_roll,
                    'advantage_mod': None,
                    'adv_info': None,
                    'damage': damage_roll,
                    'spell_save': save,
                    'dc': dc,
                    'cover_ac': None,
                    'type': 'spell_damage',
                    'spell': self.properties
                })

                # Push 10 ft (2 squares) away from the caster if possible
                push_to = tgt.push_from(battle_map, src_pos[0], src_pos[1], distance=10)
                results.append({
                    'type': 'thunderwave_push',
                    'source': entity,
                    'target': tgt,
                    'refresh_map': True,
                    'map': battle_map,
                    'push_to': push_to
                })
            else:
                # Half damage on a successful save
                half_value = damage_roll.half()
                results.append({
                    'source': entity,
                    'target': tgt,
                    'attack_name': 'thunderwave',
                    'damage_type': self.properties.get('damage_type', 'thunder'),
                    'attack_roll': None,
                    'damage_roll': damage_roll,
                    'advantage_mod': None,
                    'adv_info': None,
                    'damage': half_value,
                    'spell_save': save,
                    'dc': dc,
                    'cover_ac': None,
                    'type': 'spell_damage',
                    'spell': self.properties
                })

        return results

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
