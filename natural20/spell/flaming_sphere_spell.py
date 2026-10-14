"""Flaming Sphere — 2nd-level conjuration (SRD), concentration, 1 minute.

A 5-foot sphere of fire appears in an unoccupied space within 60 feet. Any
creature that ends its turn within 5 feet of it makes a Dexterity save,
taking 2d6 fire damage on a failure or half on a success (+1d6 per slot
level above 2nd). As a bonus action the caster can move the sphere up to 30
feet; ramming it into a creature forces the same save and stops the sphere
(``natural20.actions.flaming_sphere_action.FlamingSphereAction``).
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.objects.flaming_sphere import FlamingSphereTile
from natural20.spell.spell import Spell


class FlamingSphereEffect:
    """Concentration handle for an active sphere; dismissing it removes the sphere."""

    def __init__(self, source, zone):
        self.source = source
        self.zone = zone
        self.last_move_turn = None

    @property
    def id(self):
        return 'flaming_sphere'

    def __str__(self):
        return 'flaming_sphere'

    def label(self):
        return 'Flaming Sphere'

    def dismiss(self, entity, _descriptor=None, opts=None):
        if self.zone is not None and not isinstance(self.zone, str):
            self.zone.dismiss()


class FlamingSphereZone(PersistentAoEZone):
    __slots__ = ('source', 'center', 'dc', 'dice', '_tile_objects')

    def __init__(self, source, battle, battle_map, center, spell, *, dc, dice, duration_rounds=10):
        center = (int(center[0]), int(center[1]))
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=[center],
            name='flaming_sphere',
            shape='sphere',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.center = center
        self.dc = int(dc)
        self.dice = dice
        self._tile_objects = []

    # A creature "within 5 feet" of the sphere: any square adjacent to it.
    def contains(self, pos):
        cx, cy = self.center
        return max(abs(int(pos[0]) - cx), abs(int(pos[1]) - cy)) <= 1

    def entity_within_reach(self, entity):
        squares = self.map.entity_squares(entity) if self.map is not None else []
        if not squares:
            pos = self.map.position_of(entity) if self.map is not None else None
            squares = [pos] if pos else []
        return any(self.contains(sq) for sq in squares)

    def burn(self, entity, reason='end_of_turn'):
        """Dexterity save for half; returns the save roll (or ``None``)."""
        if entity is None or entity.dead() or self._dismissed:
            return None
        from natural20.utils.attack_util import damage_event
        roll = entity.save_throw('dexterity', self.battle, {'is_magical': True, 'dc': self.dc})
        success = roll.result() >= self.dc
        damage = DieRoll.roll(self.dice, battle=self.battle, entity=self.source,
                              description='dice_roll.spells.flaming_sphere')
        session = self.source.session
        session.event_manager.received_event({
            'event': 'flaming_sphere_save',
            'source': self.source,
            'target': entity,
            'roll': roll,
            'dc': self.dc,
            'save_type': 'dexterity',
            'success': success,
            'reason': reason,
        })
        damage_event({
            'source': self.source,
            'target': entity,
            'damage': damage.half() if success else damage,
            'damage_type': 'fire',
            'attack_name': 'flaming_sphere',
        }, self.battle)
        return roll

    def on_turn_end(self, entity):
        self.burn(entity, reason='end_of_turn')

    def move_to(self, pos):
        pos = (int(pos[0]), int(pos[1]))
        self.center = pos
        self.squares = [pos]
        for tile in list(self._tile_objects):
            try:
                if self.map is not None and tile in self.map.interactable_objects:
                    self.map.remove(tile)
                    self.map.place_object(tile, pos[0], pos[1])
            except Exception:
                pass

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


def active_sphere(caster):
    effect = getattr(caster, 'concentration', None)
    if isinstance(effect, FlamingSphereEffect) and isinstance(effect.zone, FlamingSphereZone) \
            and not effect.zone._dismissed:
        return effect
    return None


class FlamingSphereSpell(DamageScalingMixin, Spell):
    BASE_DAMAGE = '2d6'
    PER_SLOT_DAMAGE = '1d6'
    BASE_LEVEL = 2

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_empty_space',
                'num': 1,
                'range': self.properties.get('range', 60),
            }],
            'next': set_target,
        }

    def damage_dice(self, opts=None):
        return self._scaled_damage_dice(self.BASE_DAMAGE, self.PER_SLOT_DAMAGE,
                                        self._resolve_at_level(opts), base_level=self.BASE_LEVEL)

    def avg_damage(self, battle, opts=None):
        return DieRoll.roll(self.damage_dice(opts)).expected()

    def resolve(self, entity, battle, spell_action, battle_map):
        center = spell_action.target
        if hasattr(center, 'entity_uid') and battle_map is not None:
            center = battle_map.position_of(center)
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            return [{
                'type': 'spell_miss', 'source': entity, 'target': entity,
                'attack_name': 'flaming_sphere', 'message': 'invalid_area',
                'spell': self.properties,
            }]
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        return [{
            'type': 'flaming_sphere',
            'source': entity,
            'target': [int(center[0]), int(center[1])],
            'dc': dc,
            'dice': self.damage_dice({'at_level': getattr(spell_action, 'at_level', None)}),
            'effect': self,
            'spell': self.properties,
            'map': battle_map,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'flaming_sphere':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None
        duration = int((item.get('spell') or {}).get('duration_seconds', 60))
        zone = FlamingSphereZone(source, battle, battle_map, item['target'], item.get('effect'),
                                 dc=item['dc'], dice=item['dice'], duration_rounds=duration // 6)
        tile = FlamingSphereTile(session, battle_map, source, zone)
        battle_map.place_object(tile, zone.center[0], zone.center[1])
        zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)

        effect = FlamingSphereEffect(source, zone)
        source.add_casted_effect({
            'target': zone,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)
        session.event_manager.received_event({
            'event': 'flaming_sphere',
            'source': source,
            'target': list(zone.center),
            'spell': item.get('effect'),
        })
        return zone
