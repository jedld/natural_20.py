from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll


def _spell_dc(entity):
    return entity.spell_save_dc('intelligence')


class WallOfFireSpell(Spell):
    """Wall of Fire: Creates a wall of fire that deals fire damage when creatures pass through it.
    
    D&D 5e: 80-ft long, 20-ft high, 1-ft thick wall. 20d8 fire damage on first entry (Dex save for half),
    5d8 on subsequent entries.
    """

    TARGET_TYPES = ['point']

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_square',
                    'num': 1,
                    'range': self.properties.get('range', 120),
                }
            ],
            'next': set_target
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if not target:
            return []

        # Calculate wall squares based on target position
        wall_squares = self._calculate_wall_squares(battle_map, target, entity)

        # Check for creatures in the wall - they take damage and are pushed
        dc = _spell_dc(entity)
        result = []

        for wx, wy in wall_squares:
            for e in battle_map.entities_at(wx, wy):
                if e is not entity:
                    save_roll = DieRoll.roll(f"1d20 + {e.bonuses().get('dex', 0)}",
                                              battle=battle, entity=e,
                                              description=f"{e.name} Dex save vs Wall of Fire")
                    if save_roll.total >= dc:
                        damage = DieRoll.roll("10d8", battle=battle, entity=entity,
                                               description="Wall of Fire damage (successful save)")
                        result.extend([{
                            "type": "spell_damage",
                            "source": entity,
                            "target": e,
                            "attack_name": "wall_of_fire",
                            "damage_type": "fire",
                            "damage_roll": damage,
                            "save_roll": save_roll,
                            "save_dc": dc,
                            "save_bonus": e.bonuses().get('dex', 0),
                            "spell": self.properties
                        }])
                    else:
                        damage = DieRoll.roll("20d8", battle=battle, entity=entity,
                                               description="Wall of Fire damage (failed save)")
                        result.extend([{
                            "type": "spell_damage",
                            "source": entity,
                            "target": e,
                            "attack_name": "wall_of_fire",
                            "damage_type": "fire",
                            "damage_roll": damage,
                            "save_roll": save_roll,
                            "save_dc": dc,
                            "save_bonus": e.bonuses().get('dex', 0),
                            "spell": self.properties
                        }])

        # Store wall data for persistent zone damage (on subsequent turns)
        result.append({
            'type': 'wall_of_fire_zone',
            'source': entity,
            'squares': wall_squares,
            'spell': self.properties,
            'caster_dc': dc,
            'duration': self.properties.get('duration_seconds', 600),
        })

        return result

    def _calculate_wall_squares(self, battle_map, target, source):
        """Calculate wall squares extending from target position."""
        if battle_map is None:
            return []

        # Default: wall extends vertically from target position
        tx, ty = target
        wall_squares = []

        # Create a 1-tile thick wall, 8 tiles long, extending upward
        for i in range(8):
            wall_squares.append((tx, ty - i))

        return wall_squares

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'wall_of_fire_zone':
            return
        if battle and session is None:
            session = battle.session

        source = item.get('source')
        squares = item.get('squares', [])
        duration = item.get('duration', 600)
        caster_dc = item.get('caster_dc', 15)

        # Register the wall as an active effect/zone on the battle
        wall_id = f"wall_of_fire_{id(source)}_{len(battle.active_effects) if battle else 0}"

        if battle:
            battle.active_effects[wall_id] = {
                'type': 'wall_of_fire',
                'squares': squares,
                'source': source,
                'dc': caster_dc,
                'damage': '20d8',
                'duration': duration,
            }

            # Schedule wall removal
            def remove_wall():
                if wall_id in battle.active_effects:
                    del battle.active_effects[wall_id]
                # Also emit stop effect to client
                if hasattr(battle, 'session') and battle.session:
                    session = battle.session
                    if hasattr(session, 'event_manager'):
                        session.event_manager.received_event({
                            'event': 'effect_stop',
                            'effect': 'wall_of_fire',
                            'source': source,
                        })

            battle.register_timer(duration, remove_wall)

        if session:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': 'Wall of Fire',
                'source': source,
                'target': None,
            })

        # Emit wall_of_fire effect to client for visual rendering
        if battle and session:
            try:
                from webapp.blueprints.helpers.runtime_state import get_socketio
                socketio = get_socketio()
                if socketio:
                    effect_payload = {
                        'effect': 'wall_of_fire',
                        'action': 'start',
                        'config': {
                            'squares': squares,
                            'intensity': 0.9,
                            'color': '#ff4500',
                            'size_px': 32,
                        },
                        'exclusive': False,  # Allow stacking with other effects
                    }
                    socketio.emit('effect:set', effect_payload)
            except Exception as e:
                # Non-critical: socket emit failure shouldn't break spell
                pass
