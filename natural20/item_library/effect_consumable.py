"""Data-driven consumables (elixirs, draughts, tonics).

Item YAML (``item_class: EffectConsumableItem``)::

    elixir_of_boldness:
      item_class: EffectConsumableItem
      type: potion
      usable: true
      consumable: true
      activation: action
      heal: 2d4                              # optional healing dice
      heal_bonus: creator_ability:intelligence
      buffs: {attack_die: 1d4, save_die: 1d4}  # see ConsumableBuffEffect
      duration_seconds: 60
      creator_riders:                         # extra benefits from the maker
        - feature: restorative_reagents
          temp_hp: 2d6
          temp_hp_bonus: creator_ability:intelligence

``creator_ability:<ability>`` adds the maker's modifier (minimum +1). The maker
is the creature recorded as ``crafted_by`` on the inventory stack.
"""

from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.entity_class.data_driven import normalize_ability
from natural20.item_library.object import Object
from natural20.utils.healing import effective_heal_roll


def _bonus(spec, creator):
    if not spec or creator is None:
        return 0
    spec = str(spec)
    if spec.startswith('creator_ability:'):
        ability = normalize_ability(spec.split(':', 1)[1])
        return max(1, int(creator.ability_mod(ability) or 0))
    try:
        return int(spec)
    except ValueError:
        return 0


def _roll(dice, bonus, description, entity, battle):
    expression = str(dice)
    if bonus:
        expression += f"+{bonus}"
    return DieRoll.roll(expression, description=description, entity=entity, battle=battle)


class EffectConsumableItem(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.properties = properties

    def consumable(self):
        return self.properties.get('consumable', True)

    def can_use(self, entity, battle):
        return True

    def build_map(self, action):
        def next_fn(target):
            action.target = target
            return action

        return {
            'param': [{'type': 'select_target', 'num': 1, 'range': 5,
                       'target_types': ['allies', 'self']}],
            'next': next_fn,
        }

    def _creator(self, entity):
        uid = self.properties.get('crafted_by')
        if not uid:
            return None
        if uid == getattr(entity, 'entity_uid', None):
            return entity
        try:
            return self.session.entity_by_uid(uid)
        except Exception:
            return None

    def resolve(self, entity, battle, action, _battle_map):
        target = getattr(action, 'target', None) or entity
        creator = self._creator(entity)
        result = {'creator': creator}
        label = self.properties.get('name') or self.name
        if self.properties.get('heal'):
            roll = _roll(self.properties['heal'], _bonus(self.properties.get('heal_bonus'), creator),
                         label, entity, battle)
            result['hp_gain_roll'] = effective_heal_roll(target, roll)
        temp_rolls = []
        for rider in self.properties.get('creator_riders') or []:
            feature = rider.get('feature')
            if creator is None or (feature and not creator.class_feature(feature)):
                continue
            if rider.get('temp_hp'):
                temp_rolls.append(_roll(rider['temp_hp'], _bonus(rider.get('temp_hp_bonus'), creator),
                                        f"{label}: {feature}", entity, battle))
        if temp_rolls:
            result['temp_hp_roll'] = max(temp_rolls, key=lambda r: r.result())
        return result

    def use(self, entity, result, session=None):
        target = result.get('target') or entity
        if result.get('hp_gain_roll') is not None:
            target.heal(effective_heal_roll(target, result['hp_gain_roll']).result())
        if result.get('temp_hp_roll') is not None:
            target.grant_temp_hp(result['temp_hp_roll'].result(), source=result.get('creator') or entity)
        buffs = self.properties.get('buffs') or {}
        if buffs:
            from natural20.effects.consumable_buff_effect import ConsumableBuffEffect
            effect = ConsumableBuffEffect(result.get('creator') or entity, target, buffs,
                                          label=self.properties.get('effect_label') or self.name)
            effect.apply_to(target, duration=self.properties.get('duration_seconds'))
            if buffs.get('fly_speed') and hasattr(target, 'fly'):
                target._granted_flight = True
                target.fly()
