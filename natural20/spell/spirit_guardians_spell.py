"""Spirit Guardians — 15-ft emanation of spirits that follows the caster.

Hostile creatures in the area have their speed halved (the zone counts as
difficult terrain for them). When one enters the area for the first time on
a turn, or starts its turn there, it makes a Wisdom save: 3d8 radiant
(necrotic for an evil caster) on a failure, half on a success; +1d8 per slot
level above 3rd. Each creature is struck at most once per turn.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.extensions.save_for_half import SaveForHalfMixin
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell


class SpiritGuardiansEffect:
    """Concentration hook: ending concentration releases the spirits."""

    def __init__(self, source, zone):
        self.source = source
        self.zone = zone

    @property
    def id(self):
        return 'spirit_guardians'

    def __str__(self):
        return 'spirit_guardians'

    def dismiss(self, entity, effect, opts=None):
        if self.zone is not None:
            self.zone.dismiss()


class SpiritGuardiansZone(PersistentAoEZone):
    __slots__ = ('source', 'dc', 'dice', 'damage_type', 'radius_ft', '_struck')

    def __init__(self, source, battle, battle_map, spell, *, dice, damage_type, dc,
                 radius_ft=15, duration_rounds=100):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=[],
            name='spirit_guardians',
            shape='emanation',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.dc = dc
        self.dice = dice
        self.damage_type = damage_type
        self.radius_ft = radius_ft
        self._struck = {}

    def area(self):
        if self.map is None or self.source not in self.map.entities:
            return set()
        return set(self.map.squares_in_emanation(self.source, self.radius_ft, include_origin=True))

    def contains(self, pos):
        return tuple(pos) in self.area()

    def occupants(self):
        return [e for e in super().occupants() if e is not self.source]

    def affects(self, entity) -> bool:
        if entity is None or entity is self.source or self.battle is None:
            return False
        if getattr(entity, 'dead', lambda: True)():
            return False
        return bool(self.battle.opposing(self.source, entity))

    def slows(self, entity, pos) -> bool:
        return self.affects(entity) and self.contains(pos)

    def _turn_key(self):
        battle = self.battle
        return (battle.current_round(), getattr(battle, 'current_turn_index', 0))

    def strike(self, entity, reason='turn_start'):
        """Wisdom save for half; returns the applied damage items."""
        if not self.affects(entity):
            return []
        key = self._turn_key()
        uid = getattr(entity, 'entity_uid', id(entity))
        if self._struck.get(uid) == key:
            return []
        self._struck[uid] = key

        from natural20.utils.attack_util import damage_event
        roll = DieRoll.roll(self.dice, battle=self.battle, entity=self.source,
                            description='dice_roll.spells.spirit_guardians')
        items = self.spell.resolve_save_for_half(
            [entity], ability='wisdom', dc=self.dc, damage_roll=roll,
            attack_name='spirit_guardians', damage_type=self.damage_type,
            battle=self.battle,
        )
        for item in items:
            item['zone_reason'] = reason
            damage_event(item, self.battle)
        return items

    def on_turn_start(self, entity):
        self.strike(entity, reason='turn_start')

    def on_enter(self, entity):
        self.strike(entity, reason='enter')


class SpiritGuardiansSpell(DamageScalingMixin, SaveForHalfMixin, Spell):
    BASE_DAMAGE = '3d8'
    PER_SLOT_DAMAGE = '1d8'
    BASE_LEVEL = 3

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_emanation',
                'num': 1,
                'radius': self.properties.get('radius', 15),
            }],
            'next': set_target,
        }

    @staticmethod
    def damage_type_for(caster):
        try:
            alignment = str(caster.alignment() or '').lower()
        except Exception:
            alignment = ''
        return 'necrotic' if 'evil' in alignment else 'radiant'

    def damage_dice(self, at_level=None):
        level = at_level or self._resolve_at_level()
        return self._scaled_damage_dice(self.BASE_DAMAGE, self.PER_SLOT_DAMAGE, level,
                                        base_level=self.BASE_LEVEL)

    def avg_damage(self, battle, opts=None):
        if battle is None or self.source is None:
            return 0
        battle_map = battle.map_for(self.source)
        if battle_map is None:
            return 0
        squares = set(battle_map.squares_in_emanation(
            self.source, self.properties.get('radius', 15), include_origin=True))
        foes = [e for e in battle.entities
                if e is not self.source and not e.dead() and battle.opposing(self.source, e)
                and tuple(battle_map.entity_or_object_pos(e) or (-1, -1)) in squares]
        per_target = DieRoll.roll(self.damage_dice(), battle=None).expected() * 0.75
        return per_target * len(foes)

    def resolve(self, entity, battle, spell_action, battle_map):
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', 3)
        return [{
            'type': 'spirit_guardians',
            'source': entity,
            'target': entity,
            'effect': self,
            'spell': self.properties,
            'map': battle_map,
            'dice': self.damage_dice(at_level),
            'damage_type': self.damage_type_for(entity),
            'dc': entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action)),
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'spirit_guardians':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        duration = int((item.get('spell') or {}).get('duration_seconds', 600))

        source.remove_effect('spirit_guardians')
        zone = SpiritGuardiansZone(
            source, battle, battle_map, item.get('effect'),
            dice=item['dice'], damage_type=item['damage_type'], dc=item['dc'],
            radius_ft=int((item.get('spell') or {}).get('radius', 15)),
            duration_rounds=max(1, duration // 6),
        )
        register_persistent_zone(zone, battle)

        effect = SpiritGuardiansEffect(source, zone)
        source.add_casted_effect({
            'target': source,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        source.register_effect('spirit_guardians', SpiritGuardiansSpell,
                               effect=effect, source=source, duration=duration)
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'spirit_guardians',
            'source': source,
            'target': source,
            'damage_type': item['damage_type'],
            'spell': item.get('effect'),
        })
        return zone
