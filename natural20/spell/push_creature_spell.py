"""Cantrips that shove one creature away with a burst of force (e.g. Gust).

Spell YAML::

    save: strength          # ability the target saves with
    push_distance: 5        # feet pushed away from the caster on a failure
    max_size: medium        # larger creatures can't be targeted

Only the creature-push use is modelled. Other uses some spells offer (pushing
an unattended object, harmless sensory effects) are narrative flavor.
"""
from __future__ import annotations

from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell

SIZE_ORDER = ['tiny', 'small', 'medium', 'large', 'huge', 'gargantuan']


def _size_rank(size):
    size = str(size or 'medium').lower()
    return SIZE_ORDER.index(size) if size in SIZE_ORDER else SIZE_ORDER.index('medium')


class PushCreatureSpell(Spell):
    def __str__(self):
        return str((self.properties or {}).get('id') or 'push_creature')

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
                'target_types': ['enemies', 'allies'],
            }],
            'next': set_target,
        }

    def too_large(self, target):
        limit = self.properties.get('max_size')
        if not limit or not hasattr(target, 'size_identifier'):
            return False
        return _size_rank(target.size_identifier()) > _size_rank(limit)

    def validate(self, battle_map, target=None, battle=None):
        super().validate(battle_map, target, battle)
        target = target if target is not None else getattr(self.action, 'target', None)
        if target is not None and not isinstance(target, (list, tuple)) and self.too_large(target):
            self.add_validation_issue('spell.push_creature.too_large')

    def compute_hit_probability(self, battle, opts=None):
        target = getattr(self.action, 'target', None)
        if target is None or isinstance(target, (list, tuple)) or self.too_large(target):
            return 0.0
        ability = str(self.properties.get('save') or 'strength')
        dc = self.source.spell_save_dc(HoldPersonSpell._caster_spell_ability(self.source, self.action))
        roll = target.save_throw(ability, battle, {'is_magical': True})
        return 1.0 - roll.prob(dc)

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, list):
            target = target[0] if target else None
        if target is None or self.too_large(target):
            return [{'type': 'push_creature', 'source': entity, 'target': target, 'success': True,
                     'too_large': True, 'spell': self.properties, 'effect': self}]
        ability = str(self.properties.get('save') or 'strength')
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        save = SaveCheck.make(target, ability, dc, battle, {'is_magical': True, 'dc': dc})
        push_to = None
        if not save.passed:
            src = battle_map.position_of(entity)
            push_to = target.push_from(battle_map, src[0], src[1],
                                       distance=int(self.properties.get('push_distance', 5)))
            if push_to is not None and tuple(push_to) == tuple(battle_map.position_of(target)):
                push_to = None
        return [{
            'type': 'push_creature',
            'source': entity,
            'target': target,
            'roll': save.roll,
            'dc': dc,
            'save_type': ability,
            'success': save.passed,
            'push_to': list(push_to) if push_to else None,
            'map': battle_map,
            'spell': self.properties,
            'effect': self,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'push_creature':
            return None
        source, target = item['source'], item['target']
        session = session or (battle.session if battle is not None else source.session)
        push_to = item.get('push_to')
        if push_to and item.get('map') is not None:
            item['map'].move_to(target, *push_to, battle)
        session.event_manager.received_event({
            'event': 'push_creature', 'source': source, 'target': target,
            'spell': (item.get('spell') or {}).get('name'),
            'success': item.get('success'), 'roll': item.get('roll'), 'dc': item.get('dc'),
            'position': push_to, 'too_large': bool(item.get('too_large')),
        })
        return target
