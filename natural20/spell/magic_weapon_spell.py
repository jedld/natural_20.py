"""Magic Weapon — 2nd-level transmutation (SRD).

Bonus Action, touch: a nonmagical weapon a willing creature (or the caster)
has equipped becomes a +1 weapon for 1 hour. YAML ``bonus_by_slot`` lists
``[slot, bonus]`` steps (2014: +2 at 4th, +3 at 6th; 2024: +2 at 3rd, +3 at
6th). The 2014 spell needs concentration; the 2024 overlay drops it.

The bonus is applied through the generic ``item_enhancement`` effect
(``natural20/utils/class_mechanics.effect_enhancement_bonus``), which adds to
attack and damage rolls with that weapon. Simplification: the enhanced weapon
does not count as "magical" for overcoming nonmagical-damage resistance.
"""
from __future__ import annotations

from natural20.spell.spell import Spell

DEFAULT_STEPS = [[2, 1], [4, 2], [6, 3]]


def weapon_is_magical(weapon) -> bool:
    if not isinstance(weapon, dict):
        return False
    return bool(weapon.get('magical') or weapon.get('magic_bonus') or weapon.get('rarity'))


def nonmagical_weapons(entity):
    session = getattr(entity, 'session', None)
    if session is None or not hasattr(entity, 'equipped_weapons'):
        return []
    out = []
    for key in entity.equipped_weapons(session):
        try:
            weapon = session.load_weapon(key)
        except Exception:
            weapon = None
        if weapon and not weapon_is_magical(weapon):
            out.append(key)
    return out


class MagicWeaponSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.weapon_key = None
        self.bonus = 1
        self.cast_level = int((details or {}).get('level') or 2)

    def __str__(self):
        return 'magic_weapon'

    def bonus_for(self, slot_level):
        steps = self.properties.get('bonus_by_slot') or DEFAULT_STEPS
        bonus = 1
        for entry in sorted(steps, key=lambda e: int(e[0])):
            if int(slot_level) >= int(entry[0]):
                bonus = int(entry[1])
        return bonus

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 5),
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }

    def validate(self, battle_map, target=None, battle=None):
        super().validate(battle_map, target, battle)
        target = target if target is not None else getattr(self.action, 'target', None)
        if target is not None and not nonmagical_weapons(target):
            self.add_validation_issue('spell.magic_weapon.no_weapon')

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target or entity
        if isinstance(target, list):
            target = target[0]
        slot_level = int(getattr(spell_action, 'at_level', None) or self.cast_level)
        candidates = nonmagical_weapons(target)
        preferred = getattr(spell_action, 'opts', None) or {}
        weapon_key = preferred.get('weapon') if preferred.get('weapon') in candidates else None
        weapon_key = weapon_key or (candidates[0] if candidates else None)
        if weapon_key is None:
            return [{
                'type': 'magic_weapon_fizzle', 'source': entity, 'target': target, 'spell': self.properties,
            }]
        self.target = target
        self.weapon_key = weapon_key
        self.cast_level = slot_level
        self.bonus = self.bonus_for(slot_level)
        return [{
            'type': 'magic_weapon',
            'source': entity,
            'target': target,
            'effect': self,
            'weapon': weapon_key,
            'bonus': self.bonus,
            'spell': self.properties,
        }]

    @staticmethod
    def item_enhancement(entity, opts=None):
        opts = opts or {}
        effect = opts.get('effect')
        value = int(opts.get('value') or 0)
        if effect is None or getattr(effect, 'weapon_key', None) not in (opts.get('item_keys') or set()):
            return value
        return value + int(getattr(effect, 'bonus', 0) or 0)

    @staticmethod
    def apply(battle, item, session=None):
        kind = item.get('type')
        if kind not in ('magic_weapon', 'magic_weapon_fizzle'):
            return None
        source, target = item['source'], item['target']
        session = session or (battle.session if battle is not None else source.session)
        if kind == 'magic_weapon_fizzle':
            session.event_manager.received_event({
                'event': 'magic_weapon', 'source': source, 'target': target, 'weapon': None, 'bonus': 0,
            })
            return target
        effect = item['effect']
        duration = int(effect.properties.get('duration_seconds', 3600))
        if effect.properties.get('concentration'):
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)
        source.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + duration})
        target.register_effect('item_enhancement', MagicWeaponSpell, effect=effect, source=source,
                               duration=duration)
        session.event_manager.received_event({
            'event': 'magic_weapon', 'source': source, 'target': target,
            'weapon': item.get('weapon'), 'bonus': item.get('bonus'),
        })
        return target

    def dismiss(self, entity, _descriptor=None, opts=None):
        target = self.target
        if target is not None and target is not entity and hasattr(target, 'remove_effect'):
            self.target = None
            target.remove_effect(self)
