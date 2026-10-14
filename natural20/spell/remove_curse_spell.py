"""Remove Curse — 3rd-level abjuration (SRD), touch, instantaneous.

Every curse affecting the touched creature ends (see ``natural20.utils.curses``
for what counts as a curse). A cursed magic item the creature is attuned to
keeps its curse, but the creature's attunement is broken so the item can be
removed — recorded in ``properties['curse_broken_items']``.
"""
from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.utils.curses import break_curses


class RemoveCurseSpell(Spell):
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
        self.clear_validation_errors()
        self.errors = []
        target = target if target is not None else self.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else None
        if target is None or isinstance(target, str):
            self.errors.append('Invalid target')
        return len(self.errors) == 0

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            target = target[0]
        return [{
            'type': 'remove_curse',
            'source': entity,
            'target': target,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'remove_curse':
            return None
        if battle is not None and session is None:
            session = battle.session
        target = item['target']
        summary = break_curses(target, session)
        item['ended_curses'] = summary
        if session is not None:
            session.event_manager.received_event({
                'event': 'remove_curse',
                'source': item['source'],
                'target': target,
                'spell': item['effect'],
                'ended': summary['effects'],
                'status_cleared': summary['status_cleared'],
                'items': summary['items'],
            })
        return target
