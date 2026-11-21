"""Protection from Evil and Good (SRD 5.1 / 5.2.1).

One willing touched creature is protected against aberrations, celestials,
elementals, fey, fiends, and undead for the duration:

* Those creature types have disadvantage on attack rolls against the target.
  This is a ``targeted_advantage_override`` effect, read by
  ``natural20.weapons.compute_advantages_and_disadvantages`` for weapon *and*
  spell attacks.
* The target can't be charmed, frightened, or possessed by them. This is a
  source-aware ``condition_immunity`` effect read by
  ``Entity.immune_to_condition(condition, source=...)``.

The listed types come from the spell YAML ``protection_evil_and_good.creature_types``
(default: the six SRD types) so similar auras/relics can reuse the mechanic.
"""
from __future__ import annotations

import re

from natural20.spell.spell import Spell

EFFECT_KEY = 'protection_from_evil_and_good'

PROTECTED_TYPES = ['aberration', 'celestial', 'elemental', 'fey', 'fiend', 'undead']


class ProtectionEvilAndGoodEffect:
    """Per-casting effect registered on the warded creature."""

    def __init__(self, source, spell_properties):
        self.source = source
        self.spell_properties = dict(spell_properties or {})

    @property
    def id(self):
        return EFFECT_KEY

    def __str__(self):
        return EFFECT_KEY

    def creature_types(self):
        rule = self.spell_properties.get('protection_evil_and_good') or {}
        types = rule.get('creature_types') or PROTECTED_TYPES
        return [str(t).strip().lower() for t in types if str(t).strip()]

    def source_matches(self, attacker):
        """True when ``attacker`` is one of the protected creature types."""
        if attacker is None or attacker is self.source:
            return False
        from natural20.utils.monster_traits import _creature_types_of
        words = set()
        for descriptor in _creature_types_of(attacker):
            words.update(re.findall(r'[a-z]+', str(descriptor).lower()))
        return bool(words & set(self.creature_types()))

    @staticmethod
    def targeted_advantage_override(entity, opts=None):
        """Listed creature types attack the warded creature at disadvantage."""
        opts = opts or {}
        value = opts.get('value')
        advantages, disadvantages = list(value) if value else ([], [])
        effect = opts.get('effect')
        if effect is not None and effect.source_matches(opts.get('source')):
            if EFFECT_KEY not in disadvantages:
                disadvantages.append(EFFECT_KEY)
        return [advantages, disadvantages]

    @staticmethod
    def condition_immunity(entity, opts=None):
        """The warded creature can't be charmed, frightened, or possessed by
        the listed creature types (only when the effect's source is one)."""
        opts = opts or {}
        found = list(opts.get('value') or [])
        effect = opts.get('effect')
        if effect is not None and effect.source_matches(opts.get('source')):
            for condition in ('charmed', 'frightened', 'possessed'):
                if condition not in found:
                    found.append(condition)
        return found

    def dismiss(self, entity, _descriptor=None, opts=None):
        for key in ('targeted_advantage_override', 'condition_immunity', EFFECT_KEY):
            entity.effects[key] = [
                d for d in entity.effects.get(key, []) if d.get('effect') is not self
            ]
        if EFFECT_KEY in entity.statuses:
            entity.statuses.remove(EFFECT_KEY)


class ProtectionFromEvilAndGoodSpell(Spell):
    """1st-level concentration buff: disadvantage on attacks by, and immunity
    to the charm/fear/possession of, aberrations/celestials/elementals/fey/
    fiends/undead."""

    TARGET_TYPES = ['allies', 'self']

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties.get('range', 30),
                    'target_types': self.TARGET_TYPES
                }
            ],
            'next': set_target
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target or entity
        return [{
            'type': 'wizard_spell_effect',
            'source': entity,
            'target': target,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'wizard_spell_effect':
            return
        if battle and session is None:
            session = battle.session
        target = item.get('target')
        source = item.get('source')
        spell = item.get('spell') or {}
        if target is None:
            return

        duration = int(spell.get('duration_seconds', 600))  # 10 minutes default
        effect = ProtectionEvilAndGoodEffect(source, spell)
        for key in ('targeted_advantage_override', 'condition_immunity', EFFECT_KEY):
            target.register_effect(key, ProtectionEvilAndGoodEffect,
                                    effect=effect, source=source, duration=duration)

        if EFFECT_KEY not in target.statuses:
            target.statuses.append(EFFECT_KEY)

        target.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + duration if session else None})

        if spell.get('concentration'):
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            elif source is not None:
                source.concentration_on(effect)

        if session:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': 'Protection from Evil and Good',
                'source': source,
                'target': target,
            })
