"""Message cantrip — private whisper link between caster and one creature."""

from __future__ import annotations

from natural20.spell.message_spell_link import create_message_spell_link
from natural20.spell.spell import Spell
from natural20.utils.message_spell_path import MESSAGE_RANGE_FT, message_spell_reachable
from natural20.utils.target_validation import add_validation_issue


class MessageSpell(Spell):
    TARGET_TYPES = ['allies', 'enemies']

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', MESSAGE_RANGE_FT),
                'target_types': self.properties.get('target_types') or self.TARGET_TYPES,
            }],
            'next': set_target,
        }

    def validate(self, battle_map, target=None, battle=None):
        super().validate(battle_map, target, battle=battle)
        if target is None:
            add_validation_issue(self, 'validation.targeting.required')
            return
        if target is self.source:
            add_validation_issue(self, 'validation.targeting.self')
            return
        if battle_map is None:
            add_validation_issue(self, 'validation.targeting.invalid_position')
            return
        if self.source not in battle_map.entities or target not in battle_map.entities:
            add_validation_issue(self, 'validation.targeting.unavailable')
            return
        feet_per_grid = float(getattr(battle_map, 'feet_per_grid', 5) or 5)
        range_ft = float(self.properties.get('range', MESSAGE_RANGE_FT))
        if battle_map.distance(self.source, target) * feet_per_grid > range_ft + 1e-9:
            add_validation_issue(
                self,
                'validation.targeting.out_of_range',
                distance_ft=int(battle_map.distance(self.source, target) * feet_per_grid),
                range_ft=int(range_ft),
            )
            return
        if not message_spell_reachable(battle_map, self.source, target, range_ft=range_ft):
            add_validation_issue(self, 'spell.message.blocked')

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if target is None or target is entity:
            return [{
                'type': 'message_spell_failed',
                'source': entity,
                'target': target,
                'reason': 'invalid_target',
                'effect': self,
                'spell': self.properties,
            }]

        range_ft = float(self.properties.get('range', MESSAGE_RANGE_FT))
        if not message_spell_reachable(battle_map, entity, target, range_ft=range_ft):
            return [{
                'type': 'message_spell_failed',
                'source': entity,
                'target': target,
                'reason': 'blocked',
                'effect': self,
                'spell': self.properties,
            }]

        return [{
            'type': 'message_spell',
            'source': entity,
            'target': target,
            'map': battle_map,
            'battle': battle,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') == 'message_spell_failed':
            if session is None and battle:
                session = battle.session
            if session:
                session.event_manager.received_event({
                    'event': 'message_spell_failed',
                    'source': item.get('source'),
                    'target': item.get('target'),
                    'reason': item.get('reason'),
                    'spell': item.get('spell'),
                })
            return item.get('source')

        if item.get('type') != 'message_spell':
            return None

        if battle and session is None:
            session = battle.session
        if session is None:
            return None

        source = item['source']
        target = item['target']
        battle_map = item.get('map')
        spell_props = item.get('spell') or {}
        duration_seconds = int(spell_props.get('duration_seconds') or 6)

        link = create_message_spell_link(
            session,
            source,
            target,
            battle_map,
            battle=battle or item.get('battle'),
            duration_seconds=duration_seconds,
        )

        item['link_id'] = link.id
        item['link'] = link

        session.event_manager.received_event({
            'event': 'message_spell',
            'source': source,
            'target': target,
            'link_id': link.id,
            'spell': item.get('effect'),
        })
        return source
