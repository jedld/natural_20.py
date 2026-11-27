"""Pearl of Power (SRD) — command-word item that restores a spell slot.

Item YAML (``item_class: PearlOfPowerItem``)::

    pearl_of_power:
      item_class: PearlOfPowerItem
      usable: true
      activation: action
      requires_attunement: true
      pearl_slot_max: 3        # restored slot cap (SRD: 3rd)
      charges: 1               # per dawn (modelled as per long rest)

While worn or carried, the creature can use an action and speak the command
word to regain one expended spell slot. If the expended slot was 4th level
or higher, the new slot is 3rd level. Once used, it can't be used again
until the next dawn (the engine tracks this as a per-long-rest resource).
"""
from __future__ import annotations

from natural20.item_library.object import Object


class PearlOfPowerItem(Object):

    def consumable(self):
        return False

    def _resource_name(self):
        return f"{self.properties.get('name') or 'pearl_of_power'}_uses"

    def can_use(self, entity, battle):
        uses = int(self.properties.get('charges') or 1)
        resource = entity.get_resource(self._resource_name()) if hasattr(entity, 'get_resource') else None
        if resource is None:
            resource = entity.register_resource(self._resource_name(), uses, restore_on='long_rest')
        return resource.current > 0

    def build_map(self, action):
        def set_target(target):
            action.target = target
            return action

        return {'param': [{'type': 'select_target', 'num': 1, 'range': 0,
                           'target_types': ['self']}],
                'next': set_target}

    def resolve(self, entity, battle, action, _battle_map):
        return {}

    @staticmethod
    def _restore_slot(entity):
        """Restore one expended slot (<= max level), or a 3rd-level slot in
        place of an expended higher slot. Returns a description or None."""
        slots = getattr(entity, 'spell_slots', None) or {}
        max_level = 3
        for klass, by_level in slots.items():
            if not isinstance(by_level, dict):
                continue
            for level in sorted((int(l) for l in by_level if int(l) <= max_level),
                                reverse=True):
                current = int(by_level.get(level, 0) or 0)
                try:
                    maximum = int(entity.max_spell_slots(level, klass) or 0)
                except Exception:
                    maximum = 0
                if current < maximum:
                    by_level[level] = current + 1
                    return f"{klass} {level}{'st' if level == 1 else 'nd' if level == 2 else 'rd' if level == 3 else 'th'}-level slot"
        # Expended slot of 4th level or higher -> regain a 3rd-level slot.
        for klass, by_level in slots.items():
            if not isinstance(by_level, dict):
                continue
            higher_spent = False
            for level, current in by_level.items():
                if int(level) > max_level and int(current or 0) < int(
                        entity.max_spell_slots(int(level), klass) or 0):
                    higher_spent = True
                    break
            if not higher_spent:
                continue
            try:
                max3 = int(entity.max_spell_slots(max_level, klass) or 0)
            except Exception:
                max3 = 0
            if max3 and int(by_level.get(max_level, 0) or 0) < max3:
                by_level[max_level] = int(by_level.get(max_level, 0) or 0) + 1
                return f"{klass} 3rd-level slot (replacing a higher slot)"
        return None

    def use(self, entity, result, session=None):
        user = (result or {}).get('source') or entity
        name = self._resource_name()
        resource = user.get_resource(name) if hasattr(user, 'get_resource') else None
        if resource is None:
            resource = user.register_resource(name, int(self.properties.get('charges') or 1),
                                              restore_on='long_rest')
        if resource.current <= 0:
            return
        restored = self._restore_slot(user)
        if restored is None:
            return
        resource.consume(1)
        session = getattr(user, 'session', None) or session
        if session is not None:
            session.event_manager.received_event({
                'event': 'pearl_of_power', 'source': user, 'target': user,
                'restored': restored,
            })
