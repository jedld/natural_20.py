"""Seeming — Disguise Self for a group (SRD, 8 hours).

Each chosen creature within range gets its own disguise (same cosmetic rules
and Investigation DC as Disguise Self, see ``disguise_self_spell``).
Unwilling creatures make a Charisma save to resist; the AI and UI only offer
the caster and allies, so the save is rolled only for hostile picks.
"""
from __future__ import annotations

import copy

from natural20.spell.disguise_self_spell import EFFECT_KEY, DisguiseSelfSpell
from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.hold_person_spell import HoldPersonSpell


class SeemingSpell(DisguiseSelfSpell):
    def __str__(self):
        return 'seeming'

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {'param': [{'type': 'select_target', 'num': int(self.properties.get('max_targets', 6)),
                           'min': 1, 'range': self.properties.get('range', 30), 'unique_targets': True,
                           'auto_pick': 'any', 'target_types': ['self', 'allies']}],
                'next': set_target}

    def resolve(self, entity, battle, spell_action, battle_map):
        targets = spell_action.target
        if isinstance(targets, tuple):
            targets = list(targets)
        if not isinstance(targets, list):
            targets = [targets] if targets is not None else [entity]
        description = (getattr(spell_action, 'disguise', None)
                       or self.properties.get('default_disguise') or 'an unremarkable traveler')
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        results = []
        for target in targets:
            if not hasattr(target, 'register_effect'):
                continue
            if target is not entity and battle is not None and target in battle.entities \
                    and battle.opposing(entity, target):
                save = SaveCheck.make(target, 'charisma', dc, battle=battle, opts={'is_magical': True})
                if save.passed:
                    results.append({'type': 'spell_resist', 'source': entity, 'target': target,
                                    'attack_name': 'seeming', 'save_roll': save.roll, 'save_dc': dc,
                                    'spell': self.properties})
                    continue
            results.append({'type': 'seeming', 'source': entity, 'target': target, 'effect': self,
                            'description': str(description), 'dc': dc, 'spell': self.properties})
        return results

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'seeming':
            return None
        source, target = item['source'], item['target']
        session = session or (battle.session if battle is not None else source.session)
        duration = int(item['effect'].properties.get('duration_seconds', 28800))
        effect = copy.copy(item['effect'])
        effect.description = item['description']
        effect.dc = int(item['dc'])
        effect.seen_through_uids = ''
        target.remove_effect(EFFECT_KEY)
        target.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + duration})
        target.register_effect(EFFECT_KEY, DisguiseSelfSpell, effect=effect, source=source, duration=duration)
        session.event_manager.received_event({
            'event': 'disguise_self', 'source': target, 'target': target, 'description': item['description'],
        })
        return target
