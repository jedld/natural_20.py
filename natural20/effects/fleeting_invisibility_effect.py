"""Invisible until the start of the creature's next turn, or until it attacks,
deals damage or casts a spell (Archfey Disappearing Step and similar riders)."""

from __future__ import annotations

import uuid


class FleetingInvisibilityEffect:
    END_HOOKS = ('attack_resolved', 'spell_cast', 'dealt_damage')

    def __init__(self, target, label='Invisible'):
        self.target = target
        self.label_text = label
        self.uid = f"fleeting_invisibility:{uuid.uuid4().hex[:10]}"
        self.ended = False

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return 'fleeting_invisibility'

    def label(self):
        return self.label_text

    def start(self):
        from natural20.utils.until_next_turn import schedule
        target = self.target
        target.register_effect('fleeting_invisibility', FleetingInvisibilityEffect, effect=self, source=target)
        self.register_hooks()
        if 'invisible' not in target.statuses:
            target.statuses.append('invisible')
        schedule(target, self, target)

    def register_hooks(self):
        target = self.target
        if target is None or isinstance(target, str):
            return
        for hook in self.END_HOOKS:
            existing = (target.entity_event_hooks or {}).get(hook, [])
            if any(d.get('effect') is self for d in existing):
                continue
            target.register_event_hook(hook, FleetingInvisibilityEffect, effect=self, source=target)

    def restore_hooks(self):
        if not self.ended:
            self.register_hooks()

    def end(self, reason=None):
        if self.ended:
            return
        self.ended = True
        target = self.target
        if target is None or isinstance(target, str):
            return
        if 'invisible' in target.statuses and not self._other_invisibility(target):
            target.statuses.remove('invisible')
        for store_name in ('effects', 'entity_event_hooks'):
            store = getattr(target, store_name, None)
            if not isinstance(store, dict):
                continue
            for key, value in list(store.items()):
                store[key] = [f for f in value if f.get('effect') is not self]

    def _other_invisibility(self, target):
        for descriptor in (getattr(target, 'effects', None) or {}).get('invisible', []):
            if descriptor.get('effect') is not self:
                return True
        return False

    @staticmethod
    def _end_hook(entity, opt):
        effect = (opt or {}).get('effect')
        if isinstance(effect, FleetingInvisibilityEffect):
            effect.end('hostile_act')
        return []

    @staticmethod
    def attack_resolved(entity, opt=None):
        return FleetingInvisibilityEffect._end_hook(entity, opt)

    @staticmethod
    def dealt_damage(entity, opt=None):
        return FleetingInvisibilityEffect._end_hook(entity, opt)

    @staticmethod
    def spell_cast(entity, opt=None):
        return FleetingInvisibilityEffect._end_hook(entity, opt)

    def dismiss(self, entity, _descriptor=None, opts=None):
        self.end('dismissed')
