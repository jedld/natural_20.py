"""Call Lightning — a storm cloud the caster can draw bolts from each turn.

Casting calls the first bolt: each creature within 5 ft of a point under the
cloud makes a Dexterity save, taking 3d10 lightning damage on a failure or
half on a success (+1d10 per slot level above 3rd, +1d10 more when cast
outdoors in a storm). While concentrating, the caster can use its action on
later turns to call another bolt (``CallLightningBoltAction``) at a point
within 60 ft of the cloud's center.

The spell needs open sky (``requires: [open_sky]`` in YAML): it fails
indoors unless the map's ``ceiling_height`` is at least 100 ft.
"""
from __future__ import annotations

from natural20.spell.wizard_spells import AreaSaveSpell, _spell_dc
from natural20.utils.spell_requirements import is_stormy


class CallLightningEffect:
    """Concentration marker holding the storm cloud's state."""

    def __init__(self, source, center, at_level, stormy, dc, spell_properties=None):
        self.source = source
        self.center = [int(center[0]), int(center[1])]
        self.at_level = int(at_level)
        self.stormy = bool(stormy)
        self.dc = int(dc)
        self.spell_properties = spell_properties or {}
        self.last_bolt_turn = None

    @property
    def id(self):
        return 'call_lightning'

    def __str__(self):
        return 'call_lightning'

    def bolt_dice(self):
        dice = 3 + max(0, self.at_level - 3) + (1 if self.stormy else 0)
        return f"{dice}d10"

    def cloud_radius_ft(self):
        return int(self.spell_properties.get('cloud_radius', 60))

    def dismiss(self, entity, effect, opts=None):
        return None


class CallLightningSpell(AreaSaveSpell):
    BASE_DAMAGE = '3d10'
    PER_SLOT_DAMAGE = '1d10'
    BASE_LEVEL = 3
    SHAPE = 'radius'
    DAMAGE_TYPE = 'lightning'

    def avg_damage(self, battle, opts=None):
        from natural20.die_roll import DieRoll
        at_level = self._resolve_at_level(opts)
        dice = 3 + max(0, at_level - 3)
        return DieRoll.roll(f"{dice}d10", battle=None).expected() * 0.75

    def bolt_items(self, entity, battle, battle_map, center, dice, dc):
        from natural20.die_roll import DieRoll
        targets = self._target_entities(entity, battle_map, center)
        return self.resolve_save_for_half(
            targets,
            ability='dexterity',
            dc=dc,
            damage_roll=lambda _t: DieRoll.roll(dice, battle=battle, entity=entity,
                                                description='dice_roll.spells.call_lightning'),
            attack_name=self.properties.get('id', 'call_lightning'),
            damage_type='lightning',
            battle=battle,
        )

    def resolve(self, entity, battle, spell_action, battle_map):
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', 3)
        dc = _spell_dc(entity, spell_action)
        center = [int(spell_action.target[0]), int(spell_action.target[1])]
        effect = CallLightningEffect(entity, center, at_level, is_stormy(battle_map), dc, self.properties)
        items = self.bolt_items(entity, battle, battle_map, center, effect.bolt_dice(), dc)
        items.append({
            'type': 'call_lightning',
            'source': entity,
            'target': center,
            'effect': self,
            'storm': effect,
            'spell': self.properties,
        })
        return items

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'call_lightning':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        storm = item['storm']
        if battle is not None:
            storm.last_bolt_turn = (battle.current_round(), getattr(battle, 'current_turn_index', 0))
        duration = int((item.get('spell') or {}).get('duration_seconds', 600))

        source.remove_effect('call_lightning')
        source.add_casted_effect({
            'target': source,
            'effect': storm,
            'expiration': session.game_time + duration,
        })
        source.register_effect('call_lightning', CallLightningSpell, effect=storm, source=source,
                               duration=duration)
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, storm)
        else:
            source.concentration_on(storm)

        session.event_manager.received_event({
            'event': 'call_lightning',
            'source': source,
            'target': item.get('target'),
            'stormy': storm.stormy,
            'spell': item.get('effect'),
        })
        return storm
