from __future__ import annotations

from natural20.spell.spell import Spell

_MIRROR_THRESHOLDS = {3: 6, 2: 8, 1: 11}


class MirrorImageSpell(Spell):
  """Mirror Image (2nd-level illusion).

  Creates three illusory duplicates. While any remain, attack rolls against
  the caster may destroy a duplicate instead (5e d20 table).
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
    for effects in (getattr(target, 'effects', {}) or {}).values():
      for entry in effects or []:
        effect = entry.get('effect')
        if isinstance(effect, MirrorImageSpell):
          return max(0, int(getattr(effect, 'images_remaining', 0) or 0))
    return 0

  @staticmethod
  def _attack_d20_face(attack_roll):
    if attack_roll is None:
      return None
    rolls = getattr(attack_roll, 'rolls', None)
    if rolls:
      face = rolls[0]
      return face.result() if hasattr(face, 'result') else face
    if hasattr(attack_roll, 'result'):
      return attack_roll.result()
    return None

  @staticmethod
  def mirror_image_redirect(target, attack_roll, battle=None):
    """Return True when the attack destroys a duplicate instead of hitting the caster."""
    if target is None or attack_roll is None:
      return False
    if 'mirror_image' not in getattr(target, 'statuses', []):
      return False

    images = MirrorImageSpell._images_remaining(target)
    if images <= 0:
      return False

    threshold = _MIRROR_THRESHOLDS.get(images)
    if threshold is None:
      return False

    d20 = MirrorImageSpell._attack_d20_face(attack_roll)
    if d20 is None or d20 < threshold:
      return False

    MirrorImageSpell._consume_image(target)
    return True

  @staticmethod
  def _consume_image(target):
    for effects in (getattr(target, 'effects', {}) or {}).values():
      for entry in effects or []:
        effect = entry.get('effect')
        if isinstance(effect, MirrorImageSpell):
          effect.consume_image()
          return

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
    if battle is not None and hasattr(battle, 'start_concentration'):
      battle.start_concentration(item['source'], effect)
    else:
      item['source'].concentration_on(effect)

    session.event_manager.received_event({
      'event': 'spell_buf',
      'spell': item.get('spell', {}).get('label') or 'Mirror Image',
      'source': item['source'],
      'target': target,
    })
