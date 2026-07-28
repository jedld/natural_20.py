from __future__ import annotations

from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.spell import Spell


def _spell_dc(entity, spell_action=None):
  ability = HoldPersonSpell._caster_spell_ability(entity, spell_action)
  return entity.spell_save_dc(ability)


class HoldPersonSpell(Spell):
  """Hold Person (2nd-level enchantment, concentration, up to 1 minute).

  Wisdom save or paralyzed; repeat save at end of each of the target's turns.
  """

  TARGET_TYPES = ['enemies']

  def build_map(self, orig_action):
    additional_targets = 0
    if orig_action.at_level > 2:
      additional_targets = orig_action.at_level - 2

    def set_target(target):
      action = orig_action.clone()
      action.target = target
      return action

    return {
      'param': [{
        'type': 'select_target',
        'num': 1 + additional_targets,
        'range': self.properties.get('range', 60),
        'unique_targets': True,
        'target_types': self.TARGET_TYPES,
        'require_humanoid': True,
      }],
      'next': set_target,
    }

  def _targets_within_ft(self, battle_map, targets, max_ft):
    if len(targets) <= 1:
      return True
    for i, first in enumerate(targets):
      for second in targets[i + 1:]:
        if battle_map.distance(first, second) * battle_map.feet_per_grid > max_ft:
          return False
    return True

  def resolve(self, entity, battle, spell_action, battle_map):
    targets = spell_action.target
    if not targets:
      return [{
        'type': 'spell_miss',
        'source': entity,
        'target': entity,
        'attack_name': 'hold_person',
        'message': 'no_target',
        'spell': self.properties,
      }]

    if not isinstance(targets, list):
      targets = [targets]

    targets = [t for t in targets if getattr(t, 'humanoid', lambda: False)()]
    if not targets:
      return [{
        'type': 'spell_miss',
        'source': entity,
        'target': entity,
        'attack_name': 'hold_person',
        'message': 'not_humanoid',
        'spell': self.properties,
      }]

    if battle_map and not self._targets_within_ft(battle_map, targets, 30):
      return [{
        'type': 'spell_miss',
        'source': entity,
        'target': entity,
        'attack_name': 'hold_person',
        'message': 'targets_too_far_apart',
        'spell': self.properties,
      }]

    dc = _spell_dc(entity, spell_action)
    results = []
    for target in targets:
      save = SaveCheck.make(
        target, 'wisdom', dc, battle=battle,
        opts={'is_magical': True},
      )
      if save.passed:
        results.append({
          'type': 'spell_resist',
          'source': entity,
          'target': target,
          'attack_name': 'hold_person',
          'save_roll': save.roll,
          'save_dc': dc,
          'spell': self.properties,
        })
      else:
        results.append({
          'type': 'hold_person',
          'source': entity,
          'target': target,
          'attack_name': 'hold_person',
          'save_roll': save.roll,
          'save_dc': dc,
          'spell': self.properties,
          'effect': self,
        })
    return results

  @staticmethod
  def end_of_turn(entity, opt=None):
    opt = opt or {}
    effect = opt.get('effect')
    battle = opt.get('battle')
    source = opt.get('source')
    if effect is None or battle is None or source is None:
      return

    dc = _spell_dc(source)
    save = SaveCheck.make(
      entity, 'wisdom', dc, battle=battle,
      opts={'is_magical': True},
    )
    if save.passed:
      entity.dismiss_effect(effect)

  @staticmethod
  def apply(battle, item, session=None):
    if item.get('type') != 'hold_person':
      return None

    if session is None:
      session = battle.session if battle else item['source'].session

    target = item['target']
    source = item['source']
    effect = item['effect']
    duration_seconds = int(effect.properties.get('duration_seconds', 60))

    source.add_casted_effect({
      'target': target,
      'effect': effect,
      'expiration': session.game_time + duration_seconds,
    })

    if source.current_concentration() != effect:
      if battle is not None and hasattr(battle, 'start_concentration'):
        battle.start_concentration(source, effect)
      else:
        source.concentration_on(effect)

    target.register_effect(
      'hold_person', HoldPersonSpell,
      effect=effect, source=source, duration=duration_seconds,
    )
    target.register_event_hook(
      'end_of_turn', HoldPersonSpell,
      effect=effect, source=source, duration=duration_seconds,
    )

    if 'paralyzed' not in target.statuses:
      target.statuses.append('paralyzed')
    if 'incapacitated' not in target.statuses:
      target.statuses.append('incapacitated')

    session.event_manager.received_event({
      'event': 'spell_debuff',
      'spell': effect,
      'source': source,
      'target': target,
    })
    return target

  def dismiss(self, entity, _descriptor=None, opts=None):
    if 'paralyzed' in getattr(entity, 'statuses', []):
      entity.statuses.remove('paralyzed')
    if 'incapacitated' in getattr(entity, 'statuses', []):
      entity.statuses.remove('incapacitated')

  @staticmethod
  def _caster_spell_ability(entity, spell_action=None):
    spellcasting_class = getattr(spell_action, 'spellcasting_class', None)
    if spellcasting_class:
      class_info = entity.session.load_class(spellcasting_class.lower())
      if class_info:
        ability = class_info.get('spellcasting_ability')
        if ability:
          return ability

    for attr in ('spell_ability', 'spellcasting_ability'):
      getter = getattr(entity, attr, None)
      if callable(getter):
        try:
          val = getter()
          if val:
            return val
        except Exception:
          pass

    return 'wisdom'
