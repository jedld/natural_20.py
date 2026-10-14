"""Ray of Sickness — 1st-level necromancy (SRD), ranged spell attack, 60 ft.

On a hit the target takes 2d8 poison damage (+1d8 per slot level above 1st)
and makes a Constitution save; on a failure it is poisoned until the end of
the caster's next turn.
"""
from __future__ import annotations

import uuid

from natural20.die_roll import DieRoll
from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.utils.spell_attack_util import evaluate_spell_attack


class RaySicknessPoison:
    """Poisoned until the end of the caster's next turn."""

    def __init__(self, source, target, added_status=True):
        self.source = source
        self.target = target
        self.added_status = bool(added_status)
        self.armed = False
        self.uid = f"ray_of_sickness:{uuid.uuid4().hex[:10]}"
        self.ended = False

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return 'ray_of_sickness'

    def label(self):
        return 'Ray of Sickness'

    @staticmethod
    def start_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is not None:
            effect.armed = True
        return []

    @staticmethod
    def end_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is not None and effect.armed:
            entity.dismiss_effect(effect)
        return []

    def register_hooks(self, duration=None):
        source = self.source
        if source is None or isinstance(source, str):
            return
        for hook in ('start_of_turn', 'end_of_turn'):
            existing = (source.entity_event_hooks or {}).get(hook, [])
            if not any(d.get('effect') is self for d in existing):
                source.register_event_hook(hook, RaySicknessPoison, effect=self, duration=duration)

    def restore_hooks(self):
        if not self.ended:
            self.register_hooks()

    def dismiss(self, entity, _descriptor=None, opts=None):
        if self.ended:
            return
        self.ended = True
        target = self.target
        if target is None:
            return
        if self.added_status and 'poisoned' in (getattr(target, 'statuses', None) or []):
            target.statuses.remove('poisoned')
        if target is not entity and hasattr(target, 'remove_effect'):
            target.remove_effect(self)
        source = self.source
        if source is not None and source is not entity and hasattr(source, 'remove_effect'):
            source.remove_effect(self)


class RayOfSicknessSpell(DamageScalingMixin, AttackSpell):
    BASE_DAMAGE = '2d8'
    PER_SLOT_DAMAGE = '1d8'
    BASE_LEVEL = 1

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 60),
                'target_types': ['enemies'],
            }],
            'next': set_target,
        }

    def _damage(self, battle, crit=False, opts=None):
        dice = self._scaled_damage_dice(self.BASE_DAMAGE, self.PER_SLOT_DAMAGE,
                                        self._resolve_at_level(opts), base_level=self.BASE_LEVEL)
        return DieRoll.roll(dice, crit=crit, battle=battle, entity=self.source,
                            description='dice_roll.spells.ray_of_sickness')

    def avg_damage(self, battle, opts=None):
        return self._damage(None, opts=opts).expected()

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            target = target[0]
        hit, attack_roll, advantage_mod, cover_ac, adv_info, events = evaluate_spell_attack(
            self.session, entity, target, self.properties, battle=battle, opts={'action': spell_action})
        result = list(events)
        common = {
            'source': entity, 'target': target, 'attack_name': 'ray_of_sickness',
            'damage_type': 'poison', 'attack_roll': attack_roll, 'advantage_mod': advantage_mod,
            'adv_info': adv_info, 'cover_ac': cover_ac, 'spell': self.properties,
        }
        if not hit:
            result.append({**common, 'type': 'spell_miss'})
            return result
        damage = self._damage(battle, crit=attack_roll.nat_20(),
                              opts={'at_level': getattr(spell_action, 'at_level', None)})
        result.append({**common, 'type': 'spell_damage', 'damage_roll': damage, 'damage': damage})
        if hasattr(target, 'immune_to_condition') and target.immune_to_condition('poisoned'):
            return result
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        save = SaveCheck.make(target, 'constitution', dc, battle=battle, opts={'is_magical': True})
        result.append({
            'type': 'ray_of_sickness',
            'source': entity,
            'target': target,
            'save_roll': save.roll,
            'dc': dc,
            'poisoned': not save.passed,
            'effect': self,
            'spell': self.properties,
        })
        return result

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'ray_of_sickness':
            return None
        source, target = item['source'], item['target']
        if session is None:
            session = battle.session if battle is not None else source.session
        poisoned = bool(item.get('poisoned')) and not target.dead()
        session.event_manager.received_event({
            'event': 'ray_of_sickness',
            'source': source,
            'target': target,
            'roll': item.get('save_roll'),
            'dc': item.get('dc'),
            'poisoned': poisoned,
        })
        if not poisoned:
            return target
        added = 'poisoned' not in target.statuses
        if added:
            target.statuses.append('poisoned')
        effect = RaySicknessPoison(source, target, added_status=added)
        source.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + 12})
        target.register_effect('ray_of_sickness', RaySicknessPoison, effect=effect,
                               source=source, duration=12)
        effect.register_hooks(12)
        return target
