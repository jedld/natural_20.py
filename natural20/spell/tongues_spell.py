from __future__ import annotations

from natural20.spell.spell import Spell


class TonguesSpell(Spell):
    """Tongues: Grant the target the ability to understand and speak any language for the duration."""

    TARGET_TYPES = ['self', 'allies']

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
                    'range': self.properties.get('range', 0),
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
        status = 'tongues'

        if target and hasattr(target, 'statuses'):
            if status not in target.statuses:
                target.statuses.append(status)

        if target:
            duration = spell.get('duration_seconds', 600)
            target.register_effect(status, TonguesSpell,
                                   effect='language_understanding', source=source, duration=duration)

        if session:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': 'Tongues',
                'source': source,
                'target': target,
            })
