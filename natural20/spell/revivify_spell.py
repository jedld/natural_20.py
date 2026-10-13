"""Revivify — touch a creature that died within the last minute; it returns with 1 HP.

Targets a corpse square (``select_square`` + ``require_corpse``) limited by
``corpse_max_age_seconds`` (death time comes from ``attributes['death_info']``).
The diamond component is consumed through the YAML ``consumed_materials`` key.
Creatures that died of old age can't be revived.
"""
from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.utils.corpses import ally_corpses_only, corpses_at, is_corpse


class RevivifySpell(Spell):
    def _max_age(self):
        return int(self.properties.get('max_dead_seconds', 60))

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_square',
                'num': 1,
                'size': 5,
                'range': self.properties.get('range', 5),
                'require_corpse': True,
                'corpse_max_age_seconds': self._max_age(),
                'corpse_allies_only': True,
            }],
            'next': set_target,
        }

    def _corpse_at(self, battle_map, target, battle=None):
        if target is None:
            return None
        if hasattr(target, 'dead'):
            candidates = [target]
        elif isinstance(target, (list, tuple)) and len(target) == 2:
            candidates = corpses_at(battle_map, int(target[0]), int(target[1]),
                                    max_age_seconds=self._max_age())
            candidates = ally_corpses_only(candidates, self.source, battle) or candidates
        else:
            return None
        for corpse in candidates:
            if not is_corpse(corpse, max_age_seconds=self._max_age()):
                continue
            cause = ((corpse.attributes or {}).get('death_info') or {}).get('cause')
            if cause == 'old_age':
                continue
            return corpse
        return None

    def validate(self, battle_map, target=None, battle=None):
        self.errors = []
        target = target if target is not None else self.target
        if self._corpse_at(battle_map, target, battle) is None:
            self.errors.append('Choose a creature that died within the last minute.')

    def avg_damage(self, battle, opts=None):
        return 0

    def resolve(self, entity, battle, spell_action, battle_map):
        corpse = self._corpse_at(battle_map, spell_action.target, battle)
        if corpse is None:
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': entity,
                'attack_name': 'revivify',
                'message': 'no_recent_corpse',
                'spell': self.properties,
            }]
        return [{
            'type': 'revivify',
            'source': entity,
            'target': corpse,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'revivify':
            return None
        target = item['target']
        target.revive(hp=1, battle=battle, source=item['source'])
        return target
