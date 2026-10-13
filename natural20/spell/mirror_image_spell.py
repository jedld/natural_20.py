from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell

# 2014: d20 needed to redirect an attack, by duplicates remaining.
_MIRROR_THRESHOLDS = {3: 6, 2: 8, 1: 11}
# 2024: on a hit, roll a d6 per duplicate; any die at or above this hits one.
_D6_THRESHOLD = 3


class MirrorImageSpell(Spell):
  """Mirror Image (2nd-level illusion).

  Creates three illusory duplicates. While any remain, attacks against the
  caster may strike a duplicate instead. The ruleset picks the mechanic
  (``Ruleset.mirror_image_model``):

  * ``d20_redirect`` (2014): each attack rolls a d20 (6+/8+/11+ for 3/2/1
    duplicates). On a redirect the attack roll is compared to the duplicate's
    AC (10 + caster's Dex modifier); a hit destroys it. The caster is never hit.
  * ``d6_on_hit`` (2024): when an attack roll hits, roll a d6 per remaining
    duplicate; any 3+ means a duplicate is hit and destroyed instead.

  Attackers that are blinded, can't see the caster, or perceive the caster
  with blindsight/truesight are unaffected.
  """

  def __init__(self, session, source, spell_name, details):
    super().__init__(session, source, spell_name, details)
    self.images_remaining = 3

  def build_map(self, orig_action):
    def set_target(target):
      action = orig_action.clone()
      action.target = target
      return action

    return {
      'param': [{
        'type': 'select_target',
        'num': 1,
        'range': 0,
        'target_types': ['self'],
      }],
      'next': set_target,
    }

  def resolve(self, entity, battle, spell_action, _battle_map):
    return [{
      'type': 'mirror_image',
      'source': entity,
      'target': entity,
      'effect': self,
      'spell': self.properties,
      'images': 3,
    }]

  @staticmethod
  def _images_remaining(target):
    if target is None:
      return 0
    try:
      now = target.session.game_time
    except Exception:
      now = None
    for effects in (getattr(target, 'effects', {}) or {}).values():
      for entry in effects or []:
        effect = entry.get('effect')
        expiration = entry.get('expiration')
        if now is not None and expiration is not None and expiration <= now:
          continue
        if isinstance(effect, MirrorImageSpell):
          return max(0, int(getattr(effect, 'images_remaining', 0) or 0))
    return 0

  @staticmethod
  def images_remaining_for(target):
    if target is None or 'mirror_image' not in (getattr(target, 'statuses', None) or []):
      return 0
    return MirrorImageSpell._images_remaining(target)

  @staticmethod
  def _model(target, battle):
    session = getattr(battle, 'session', None) or getattr(target, 'session', None)
    ruleset = getattr(session, 'ruleset', None)
    try:
      return ruleset.mirror_image_model() if ruleset is not None else 'd20_redirect'
    except Exception:
      return 'd20_redirect'

  @staticmethod
  def _distance_ft(battle, attacker, target):
    try:
      battle_map = battle.map_for(attacker)
      return battle_map.distance(attacker, target) * (battle_map.feet_per_grid or 5)
    except Exception:
      return None

  @staticmethod
  def attacker_unaffected(attacker, target, battle=None):
    """True when the attacker isn't fooled by the duplicates."""
    if attacker is None:
      return False
    try:
      if attacker.blinded():
        return True
    except Exception:
      pass
    if battle is not None:
      try:
        if not battle.can_see(attacker, target):
          return True
      except Exception:
        pass
    distance = MirrorImageSpell._distance_ft(battle, attacker, target) if battle is not None else None
    props = getattr(attacker, 'properties', None) or {}
    for sense in ('blindsight', 'truesight'):
      reach = props.get(sense)
      try:
        reach = int(reach) if reach else 0
      except (TypeError, ValueError):
        reach = 0
      if reach and (distance is None or distance <= reach):
        return True
    return False

  @staticmethod
  def check_attack(attacker, target, attack_roll, hit, battle=None):
    """Resolve Mirror Image for one attack against *target*.

    Returns None when the spell plays no part (no duplicates, unaffected
    attacker, or the duplicate roll fails). Otherwise returns a dict with
    ``destroyed`` (a duplicate was hit), the duplicate ``roll``, the
    ``remaining`` count and rule details; the attack then misses the caster.
    """
    if target is None or attack_roll is None:
      return None
    images = MirrorImageSpell.images_remaining_for(target)
    if images <= 0 or MirrorImageSpell.attacker_unaffected(attacker, target, battle):
      return None

    model = MirrorImageSpell._model(target, battle)
    outcome = {'model': model, 'images': images, 'attacker': attacker, 'target': target}
    if model == 'd6_on_hit':
      if not hit:
        return None
      roll = DieRoll.roll(f"{images}d6", description='dice_roll.mirror_image', entity=target, battle=battle)
      faces = [r for r in roll.rolls if isinstance(r, int)]
      if not any(face >= _D6_THRESHOLD for face in faces):
        return None
      outcome.update({'roll': roll, 'threshold': _D6_THRESHOLD, 'destroyed': True})
    else:
      threshold = _MIRROR_THRESHOLDS.get(min(images, 3))
      roll = DieRoll.roll('1d20', description='dice_roll.mirror_image', entity=target, battle=battle)
      if roll.result() < threshold:
        return None
      duplicate_ac = 10 + int(target.dex_mod() or 0)
      if attack_roll.nat_20():
        struck = True
      elif attack_roll.nat_1():
        struck = False
      else:
        struck = attack_roll.result() >= duplicate_ac
      outcome.update({'roll': roll, 'threshold': threshold, 'duplicate_ac': duplicate_ac,
                      'destroyed': struck})

    if outcome['destroyed']:
      MirrorImageSpell._consume_image(target)
    outcome['remaining'] = MirrorImageSpell._images_remaining(target)
    return outcome

  @staticmethod
  def summary(outcome):
    """Plain data for a miss item (``item['mirror_image']``)."""
    return {k: v for k, v in outcome.items() if k not in ('attacker', 'target')}

  @staticmethod
  def emit_duplicate_event(battle, item, session=None):
    """Log a miss caused by Mirror Image in place of the plain miss line."""
    if session is None and battle is not None:
      session = battle.session
    if session is None:
      return
    info = item.get('mirror_image') or {}
    session.event_manager.received_event({
      'event': 'mirror_image_duplicate',
      'source': item['source'],
      'target': item['target'],
      'attack_name': item.get('attack_name'),
      'attack_roll': item.get('attack_roll'),
      'as_legendary_action': bool(item.get('as_legendary_action')),
      'as_reaction': bool(item.get('as_reaction')),
      'roll': info.get('roll'),
      'threshold': info.get('threshold'),
      'duplicate_ac': info.get('duplicate_ac'),
      'destroyed': info.get('destroyed', False),
      'remaining': info.get('remaining', 0),
      'model': info.get('model'),
    })

  @staticmethod
  def _consume_image(target):
    for effects in (getattr(target, 'effects', {}) or {}).values():
      for entry in effects or []:
        effect = entry.get('effect')
        if isinstance(effect, MirrorImageSpell):
          effect.consume_image()
          return

  def dismiss(self, entity, _descriptor=None, _opts=None):
    if 'mirror_image' in (getattr(entity, 'statuses', None) or []):
      entity.statuses.remove('mirror_image')

  def consume_image(self):
    self.images_remaining = max(0, int(self.images_remaining or 0) - 1)
    owner = getattr(self, 'source', None) or getattr(getattr(self, 'action', None), 'source', None)
    if self.images_remaining <= 0 and owner is not None:
      if 'mirror_image' in owner.statuses:
        owner.statuses.remove('mirror_image')
      owner.dismiss_effect(self)
    return self.images_remaining

  @staticmethod
  def apply(battle, item, session=None):
    if item.get('type') != 'mirror_image':
      return

    if battle and session is None:
      session = battle.session
    if session is None:
      return

    target = item['target']
    effect = item.get('effect')
    duration = int(item.get('spell', {}).get('duration_seconds', 60))

    if effect is not None:
      effect.images_remaining = int(item.get('images', 3) or 3)

    target.register_effect('mirror_image', MirrorImageSpell, effect=effect, source=item['source'], duration=duration)
    if 'mirror_image' not in target.statuses:
      target.statuses.append('mirror_image')

    item['source'].add_casted_effect({
      'target': target,
      'effect': effect,
      'expiration': session.game_time + duration,
    })

    session.event_manager.received_event({
      'event': 'spell_buf',
      'spell': item.get('spell', {}).get('label') or 'Mirror Image',
      'source': item['source'],
      'target': target,
    })
