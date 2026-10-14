"""Throwable consumables (Alchemist's Fire and similar flasks).

The user throws the item at a creature within YAML ``thrown_range`` feet
(default 20) and makes a ranged attack with it as an improvised weapon:
1d20 + Dexterity modifier, no proficiency bonus. On a hit the item applies
its YAML riders:

* ``damage`` / ``damage_type`` — immediate damage.
* ``burning`` — ``{damage, damage_type, extinguish_dc}``; sets the target
  alight with :class:`~natural20.effects.burning_effect.BurningEffect`.

The flask is spent whether it hits or misses (``consumable: true``).
"""

from natural20.die_roll import DieRoll
from natural20.item_library.object import Object


class ThrownFlaskItem(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.properties = properties

    def consumable(self):
        return self.properties.get('consumable', True)

    def can_use(self, entity, battle):
        return True

    def thrown_range(self):
        return int(self.properties.get('thrown_range') or 20)

    def _weapon_profile(self):
        return {
            'name': self.properties.get('name', self.name),
            'type': 'ranged_attack',
            'range': self.thrown_range(),
            'range_max': self.thrown_range(),
            'properties': ['thrown'],
        }

    def build_map(self, action):
        def next_fn(target):
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.thrown_range(),
                    'target_types': ['enemies'],
                }
            ],
            'next': next_fn,
        }

    def resolve(self, entity, battle, action, _battle_map):
        from natural20.utils.ac_utils import effective_ac
        from natural20.weapons import target_advantage_condition

        target = getattr(action, 'target', None)
        if target is None:
            return {'hit': False}
        session = self.session or entity.session
        advantage_mod, adv_info = target_advantage_condition(
            session, entity, target, self._weapon_profile(), battle=battle, thrown=True)
        dex = entity.dex_mod()
        attack_roll = DieRoll.roll(
            f"1d20{'+' if dex >= 0 else ''}{dex}",
            advantage=advantage_mod > 0,
            disadvantage=advantage_mod < 0,
            description='dice_roll.thrown_item_attack',
            entity=entity,
            battle=battle,
        )
        target_ac, _cover = effective_ac(battle, entity, target)
        if attack_roll.nat_20():
            hit = True
        elif attack_roll.nat_1():
            hit = False
        else:
            hit = attack_roll.result() >= target_ac
        result = {
            'hit': hit,
            'attack_roll': attack_roll,
            'advantage_mod': advantage_mod,
            'adv_info': adv_info,
            'target_ac': target_ac,
        }
        if hit and self.properties.get('damage'):
            result['damage_roll'] = DieRoll.roll(
                str(self.properties['damage']),
                crit=attack_roll.nat_20(),
                description='dice_roll.thrown_item_damage',
                entity=entity,
                battle=battle,
            )
        return result

    def use(self, entity, result, session=None):
        target = entity
        source = result.get('source')
        session = session or self.session or getattr(source, 'session', None)
        battle = result.get('battle')
        hit = bool(result.get('hit'))
        if session is not None:
            session.event_manager.received_event({
                'event': 'thrown_item_hit' if hit else 'thrown_item_miss',
                'source': source,
                'target': target,
                'item_label': self.properties.get('name', self.name),
                'attack_roll': result.get('attack_roll'),
            })
        if not hit or target is None or target.dead():
            return
        damage_roll = result.get('damage_roll')
        if damage_roll is not None:
            target.take_damage(damage_roll.result(), battle=battle,
                               damage_type=self.properties.get('damage_type', 'fire'),
                               session=session, roll_info=damage_roll)
        burning = self.properties.get('burning')
        if isinstance(burning, dict) and not target.dead() and not target.object():
            from natural20.effects.burning_effect import BurningEffect
            BurningEffect.apply_to(
                target, source,
                damage=burning.get('damage', '1d4'),
                damage_type=burning.get('damage_type', 'fire'),
                extinguish_dc=burning.get('extinguish_dc', 10),
                label=self.properties.get('name', 'Burning'),
            )
            if session is not None:
                session.event_manager.received_event({
                    'event': 'burning',
                    'source': source,
                    'target': target,
                    'damage': burning.get('damage', '1d4'),
                    'damage_type': burning.get('damage_type', 'fire'),
                })
