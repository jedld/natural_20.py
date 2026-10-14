"""Sanctuary — 1st-level abjuration (SRD), bonus action, 1 minute.

Wards one creature within 30 feet. Until the spell ends, any creature that
targets the warded creature with an attack or a harmful spell must first make
a Wisdom save against the caster's spell save DC; on a failure it loses the
attack or spell (see ``natural20.utils.targeting_ward``). Area effects are
not blocked. The spell ends if the warded creature makes an attack, casts a
spell that affects an enemy, or deals damage to another creature.
"""
from __future__ import annotations

import uuid

from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell


class SanctuaryEffect:
    END_HOOKS = ('attack_resolved', 'spell_cast', 'dealt_damage')

    def __init__(self, source, target, dc, label='Sanctuary'):
        self.source = source
        self.target = target
        self.dc = int(dc)
        self.label_text = label
        self.uid = f"sanctuary:{uuid.uuid4().hex[:10]}"
        self.ended = False

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return 'sanctuary'

    def label(self):
        return self.label_text

    @staticmethod
    def targeting_ward(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return None
        return {'save_type': 'wisdom', 'dc': effect.dc, 'label': effect.label()}

    @staticmethod
    def _end(entity, opt, reason):
        effect = (opt or {}).get('effect')
        if effect is None or effect.ended:
            return []
        session = getattr(entity, 'session', None)
        entity.dismiss_effect(effect)
        if session is not None:
            session.event_manager.received_event({
                'event': 'sanctuary_end',
                'source': entity,
                'target': entity,
                'reason': reason,
            })
        return []

    @staticmethod
    def attack_resolved(entity, opt=None):
        return SanctuaryEffect._end(entity, opt, 'attacked')

    @staticmethod
    def dealt_damage(entity, opt=None):
        return SanctuaryEffect._end(entity, opt, 'dealt_damage')

    @staticmethod
    def spell_cast(entity, opt=None):
        opt = opt or {}
        if SanctuaryEffect._spell_affects_enemy(entity, opt.get('action'), opt.get('battle')):
            return SanctuaryEffect._end(entity, opt, 'cast_hostile_spell')
        return []

    @staticmethod
    def _spell_affects_enemy(caster, action, battle):
        if action is None:
            return False
        affected = []
        target = getattr(action, 'target', None)
        for t in (target if isinstance(target, (list, tuple)) else [target]):
            if hasattr(t, 'entity_uid'):
                affected.append(t)
        for item in getattr(action, 'result', None) or []:
            if not isinstance(item, dict):
                continue
            for key in ('target', 'targets'):
                value = item.get(key)
                for t in (value if isinstance(value, (list, tuple)) else [value]):
                    if hasattr(t, 'entity_uid') and t not in affected:
                        affected.append(t)
        for t in affected:
            if t is caster:
                continue
            if battle is not None:
                try:
                    if battle.opposing(caster, t):
                        return True
                except Exception:
                    continue
            elif getattr(t, 'group', None) != getattr(caster, 'group', None):
                return True
        return False

    def register_hooks(self, duration=None):
        target = self.target
        if target is None or isinstance(target, str):
            return
        for hook in self.END_HOOKS:
            existing = (target.entity_event_hooks or {}).get(hook, [])
            if any(d.get('effect') is self for d in existing):
                continue
            target.register_event_hook(hook, SanctuaryEffect, effect=self,
                                       source=self.source, duration=duration)

    def restore_hooks(self):
        if not self.ended:
            self.register_hooks()

    def dismiss(self, entity, _descriptor=None, opts=None):
        if self.ended:
            return
        self.ended = True
        target = self.target
        if target is not None and target is not entity and hasattr(target, 'remove_effect'):
            target.remove_effect(self)


class SanctuarySpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 30),
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else entity
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        return [{
            'type': 'sanctuary',
            'source': entity,
            'target': target,
            'dc': dc,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'sanctuary':
            return None
        source, target = item['source'], item['target']
        if session is None:
            session = battle.session if battle is not None else source.session
        duration = int((item.get('spell') or {}).get('duration_seconds', 60))
        for descriptor in list((getattr(target, 'effects', None) or {}).get('targeting_ward', [])):
            old = descriptor.get('effect')
            if isinstance(old, SanctuaryEffect):
                target.dismiss_effect(old)
        effect = SanctuaryEffect(source, target, item['dc'],
                                 label=(item.get('spell') or {}).get('label', 'Sanctuary'))
        source.add_casted_effect({
            'target': target,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        target.register_effect('targeting_ward', SanctuaryEffect, effect=effect,
                               source=source, duration=duration)
        effect.register_hooks(duration)
        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': item.get('effect'),
            'source': source,
            'target': target,
        })
        return target
