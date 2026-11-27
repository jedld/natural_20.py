"""Investiture of Flame (Elemental Evolution) — 6th-level druid/wizard/sorcerer.

Flames race across your body for the duration (concentration, 1 minute):

- You are immune to fire damage and resistant to cold damage.
- Any creature that moves within 5 feet of you for the first time on a turn
  or ends its turn there takes 1d10 fire damage (no save).
- You can use an action to create a 15-foot line of flame (Dex save, 4d8
  fire, half on success) — see ``natural20/actions/flame_line_action.py``.

The light-shedding part is DM-narrated. The moving 5-foot aura reuses the
Spirit Guardians emanation machinery with the save skipped (``dc=100``).
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.environment_zones import register_persistent_zone
from natural20.spell.spirit_guardians_spell import SpiritGuardiansZone
from natural20.spell.spell import Spell


class InvestitureFlameAuraZone(SpiritGuardiansZone):
    """5-foot emanation of flame: 1d10 fire, no saving throw."""

    def strike(self, entity, reason='turn_start'):
        if not self.affects(entity):
            return []
        key = self._turn_key()
        uid = getattr(entity, 'entity_uid', id(entity))
        if self._struck.get(uid) == key:
            return []
        self._struck[uid] = key

        from natural20.utils.attack_util import damage_event
        roll = DieRoll.roll(self.dice, battle=self.battle, entity=self.source,
                            description='dice_roll.spells.investiture_of_flame')
        item = {
            'source': self.source,
            'target': entity,
            'attack_name': 'investiture_of_flame',
            'damage_type': self.damage_type,
            'attack_roll': None,
            'damage_roll': roll,
            'damage': roll,
            'advantage_mod': None,
            'adv_info': None,
            'zone_reason': reason,
            'spell': getattr(self.spell, 'properties', None) or {},
        }
        damage_event(item, self.battle)
        return [item]


class InvestitureOfFlameEffect:

    def __init__(self, source, zone, spell_properties=None):
        self.source = source
        self.zone = zone
        self.spell_properties = dict(spell_properties or {})

    @property
    def id(self):
        return 'investiture_of_flame'

    def __str__(self):
        return self.id

    def label(self):
        return 'Investiture of Flame'

    @staticmethod
    def immunity_override(entity, opt=None):
        opt = opt or {}
        return list(opt.get('value') or []) + ['fire']

    @staticmethod
    def resistance_override(entity, opt=None):
        opt = opt or {}
        return list(opt.get('value') or []) + ['cold']

    def dismiss(self, entity, descriptor=None, opts=None):
        if self.zone is not None:
            self.zone.dismiss()
        statuses = getattr(entity, 'statuses', None)
        if isinstance(statuses, list) and 'investiture_of_flame' in statuses:
            statuses.remove('investiture_of_flame')


class InvestitureOfFlameSpell(Spell):

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{'type': 'select_target', 'num': 1, 'range': 0,
                       'target_types': ['self']}],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        return [{
            'type': 'investiture_of_flame', 'source': entity, 'target': entity,
            'effect': self, 'spell': self.properties, 'map': battle_map,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'investiture_of_flame':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 60))

        source.remove_effect('investiture_of_flame')
        zone = InvestitureFlameAuraZone(            source, battle, battle_map, item.get('effect'),
            dice=spell.get('aura_dice', '1d10'), damage_type='fire',
            dc=100,  # no save: every affected creature takes the damage
            radius_ft=int(spell.get('aura_radius', 5)),
            duration_rounds=max(1, duration // 6),
        )
        register_persistent_zone(zone, battle)

        effect = InvestitureOfFlameEffect(source, zone, spell)
        source.add_casted_effect({'target': source, 'effect': effect,
                                  'expiration': session.game_time + duration})
        source.register_effect('investiture_of_flame', InvestitureOfFlameEffect,
                               effect=effect, source=source, duration=duration)
        source.register_effect('immunity_override', InvestitureOfFlameEffect,
                               effect=effect, source=source, duration=duration)
        source.register_effect('resistance_override', InvestitureOfFlameEffect,
                               effect=effect, source=source, duration=duration)
        statuses = getattr(source, 'statuses', None)
        if isinstance(statuses, list) and 'investiture_of_flame' not in statuses:
            statuses.append('investiture_of_flame')
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'spell_buf', 'source': source, 'target': source,
            'spell': spell, 'effect_name': 'investiture_of_flame',
        })
        return effect
