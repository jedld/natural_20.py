from __future__ import annotations

from natural20.spell.spell import Spell


class ProtectionFromEvilAndGoodSpell(Spell):
    """Protection from Evil and Good: Buff that grants AC bonus, advantage vs certain creature types, and resistance against being charmed/possessed."""

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
        status = 'protection_from_evil_and_good'

        if target and hasattr(target, 'statuses'):
            if status not in target.statuses:
                target.statuses.append(status)

        if target:
            duration = spell.get('duration_seconds', 600)  # 10 minutes default
            target.register_effect(status, ProtectionFromEvilAndGoodSpell,
                                   effect='protection', source=source, duration=duration)

        if session:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': 'Protection from Evil and Good',
                'source': source,
                'target': target,
            })

    @staticmethod
    def resistance_override(entity, opts=None):
        """Grant resistance against charmed, frightened, and possessed effects from aberrations, celestials, elementals, fey, fiends, and undead."""
        opts = opts or {}
        base = list(opts.get('value') or [])
        source = opts.get('effect')
        # Check if source is a protected creature type
        source_entity = opts.get('source_entity')
        if source_entity:
            race = getattr(source_entity, 'race', '') or ''
            protected_types = ['fiend', 'undead', 'fey', 'celestial', 'elemental', 'aberration']
            for pt in protected_types:
                if pt in race.lower():
                    return base + ['charmed', 'frightened']
        return base
