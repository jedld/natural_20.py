"""Melf's Acid Arrow — 2nd-level evocation (SRD), ranged spell attack, 90 ft.

Hit: 4d4 acid damage immediately and 2d4 acid damage at the end of the
target's next turn. Miss: half the initial damage and no delayed damage.
Both amounts increase by 1d4 per slot level above 2nd.
"""
from __future__ import annotations

import uuid

from natural20.die_roll import DieRoll
from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.utils.spell_attack_util import evaluate_spell_attack


class AcidArrowBurn:
    """Delayed acid damage dealt at the end of the target's next turn."""

    def __init__(self, source, target, dice):
        self.source = source
        self.target = target
        self.dice = dice
        self.uid = f"acid_arrow:{uuid.uuid4().hex[:10]}"
        self.ended = False

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return 'acid_arrow'

    def label(self):
        return "Melf's Acid Arrow"

    @staticmethod
    def end_of_turn(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        if effect is None or effect.ended:
            return []
        battle = opt.get('battle')
        if battle is None:
            session = getattr(entity, 'session', None)
            battle = getattr(session, 'battle', None) if session is not None else None
        entity.dismiss_effect(effect)
        if entity.dead():
            return []
        from natural20.utils.attack_util import damage_event
        damage = DieRoll.roll(effect.dice, battle=battle, entity=effect.source,
                              description='dice_roll.spells.melfs_acid_arrow')
        damage_event({
            'source': effect.source,
            'target': entity,
            'damage': damage,
            'damage_type': 'acid',
            'attack_name': 'melfs_acid_arrow_burn',
        }, battle)
        return []

    def register_hooks(self, duration=None):
        target = self.target
        if target is None or isinstance(target, str):
            return
        existing = (target.entity_event_hooks or {}).get('end_of_turn', [])
        if not any(d.get('effect') is self for d in existing):
            target.register_event_hook('end_of_turn', AcidArrowBurn, effect=self,
                                       source=self.source, duration=duration)

    def restore_hooks(self):
        if not self.ended:
            self.register_hooks()

    def dismiss(self, entity, _descriptor=None, opts=None):
        if self.ended:
            return
        self.ended = True
        for holder in (self.target, self.source):
            if holder is not None and holder is not entity and hasattr(holder, 'remove_effect'):
                holder.remove_effect(self)


class MelfsAcidArrowSpell(DamageScalingMixin, AttackSpell):
    BASE_DAMAGE = '4d4'
    BURN_DAMAGE = '2d4'
    PER_SLOT_DAMAGE = '1d4'
    BASE_LEVEL = 2

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 90),
                'target_types': ['enemies'],
            }],
            'next': set_target,
        }

    def _dice(self, base, opts=None):
        return self._scaled_damage_dice(base, self.PER_SLOT_DAMAGE,
                                        self._resolve_at_level(opts), base_level=self.BASE_LEVEL)

    def _damage(self, battle, crit=False, opts=None):
        return DieRoll.roll(self._dice(self.BASE_DAMAGE, opts), crit=crit, battle=battle,
                            entity=self.source, description='dice_roll.spells.melfs_acid_arrow')

    def avg_damage(self, battle, opts=None):
        return (DieRoll.roll(self._dice(self.BASE_DAMAGE, opts)).expected()
                + DieRoll.roll(self._dice(self.BURN_DAMAGE, opts)).expected())

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            target = target[0]
        level_opts = {'at_level': getattr(spell_action, 'at_level', None)}
        hit, attack_roll, advantage_mod, cover_ac, adv_info, events = evaluate_spell_attack(
            self.session, entity, target, self.properties, battle=battle, opts={'action': spell_action})
        result = list(events)
        common = {
            'source': entity, 'target': target, 'attack_name': 'melfs_acid_arrow',
            'damage_type': 'acid', 'attack_roll': attack_roll, 'advantage_mod': advantage_mod,
            'adv_info': adv_info, 'cover_ac': cover_ac, 'spell': self.properties,
        }
        if hit:
            damage = self._damage(battle, crit=attack_roll.nat_20(), opts=level_opts)
            result.append({**common, 'type': 'spell_damage', 'damage_roll': damage, 'damage': damage})
            result.append({
                'type': 'melfs_acid_arrow',
                'source': entity,
                'target': target,
                'burn_dice': self._dice(self.BURN_DAMAGE, level_opts),
                'effect': self,
            })
            return result
        result.append({**common, 'type': 'spell_miss'})
        damage = self._damage(battle, opts=level_opts)
        half = damage.half() if hasattr(damage, 'half') else damage.result() // 2
        if (half.result() if hasattr(half, 'result') else half) > 0:
            splash = {k: v for k, v in common.items() if k != 'attack_roll'}
            result.append({**splash, 'type': 'spell_damage', 'damage_roll': damage,
                           'damage': half, 'half_damage': True})
        return result

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'melfs_acid_arrow':
            return None
        source, target = item['source'], item['target']
        if target.dead():
            return target
        if session is None:
            session = battle.session if battle is not None else source.session
        effect = AcidArrowBurn(source, target, item['burn_dice'])
        source.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + 12})
        target.register_effect('acid_arrow', AcidArrowBurn, effect=effect,
                               source=source, duration=12)
        effect.register_hooks(12)
        session.event_manager.received_event({
            'event': 'melfs_acid_arrow',
            'source': source,
            'target': target,
            'burn_dice': item['burn_dice'],
        })
        return target
