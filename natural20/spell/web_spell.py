from __future__ import annotations

from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.environment_zones import register_persistent_zone
from natural20.spell.spell import Spell


class WebZone(PersistentAoEZone):
  """Sticky webs: Dex save or restrained while inside the zone."""

  __slots__ = ('source', 'dc', '_restrained')

  def __init__(self, source, battle, battle_map, squares, spell):
    super().__init__(
      owner=source,
      battle=battle,
      map=battle_map,
      squares=squares,
      name='web',
      shape='square',
      duration_rounds=600,  # up to 1 hour; concentration ends early
      concentration=True,
      spell=spell,
    )
    self.source = source
    self.dc = source.spell_save_dc()
    self._restrained = set()

  def _release(self, entity):
    uid = getattr(entity, 'entity_uid', None)
    if uid in self._restrained:
      self._restrained.discard(uid)
    if entity is not None and hasattr(entity, 'statuses') and 'restrained' in entity.statuses:
      entity.statuses.remove('restrained')

  def apply_save(self, entity, reason='zone'):
    if entity is None or entity.dead():
      return

    roll = entity.save_throw('dexterity', self.battle, {'is_magical': True})
    success = roll.result() >= self.dc
    became_restrained = False

    if not success:
      if 'restrained' not in getattr(entity, 'statuses', []):
        entity.statuses.append('restrained')
      self._restrained.add(entity.entity_uid)
      became_restrained = True
    else:
      self._release(entity)

    self.source.session.event_manager.received_event({
      'event': 'web_save',
      'source': self.source,
      'target': entity,
      'roll': roll,
      'dc': self.dc,
      'save_type': 'dexterity',
      'success': success,
      'reason': reason,
      'became_restrained': became_restrained,
    })

  def on_enter(self, entity):
    self.apply_save(entity, reason='enter')

  def on_turn_end(self, entity):
    if self.map is None:
      return
    try:
      pos = self.map.position_of(entity)
    except Exception:
      return
    if pos and self.contains(pos):
      self.apply_save(entity, reason='turn_end')

  def on_dismiss(self):
    for entity in list(self.occupants()):
      self._release(entity)


class WebSpell(Spell):
  """Web (2nd-level conjuration, concentration).

  A 20-foot cube of sticky webs; creatures that fail a Dexterity save are
  restrained while in the area.
  """

  def build_map(self, orig_action):
    def set_target(target):
      action = orig_action.clone()
      action.target = target
      return action

    return {
      'param': [{
        'type': 'select_square',
        'num': 1,
        'range': self.properties.get('range', 60),
        'size': self.properties.get('area_size', 20),
      }],
      'next': set_target,
    }

  def _target_squares(self, center, battle_map):
    x, y = int(center[0]), int(center[1])
    size = max(1, int(self.properties.get('area_size', 20)) // battle_map.feet_per_grid)
    squares = []
    for dx in range(size):
      for dy in range(size):
        sx, sy = x + dx, y + dy
        if 0 <= sx < battle_map.size[0] and 0 <= sy < battle_map.size[1]:
          squares.append((sx, sy))
    return squares

  def resolve(self, entity, battle, spell_action, battle_map):
    squares = self._target_squares(spell_action.target, battle_map)
    if not squares:
      return [{
        'type': 'spell_miss',
        'source': entity,
        'target': entity,
        'attack_name': 'web',
        'message': 'invalid_area',
        'spell': self.properties,
      }]

    return [{
      'type': 'web',
      'source': entity,
      'target': list(spell_action.target),
      'squares': [list(s) for s in squares],
      'effect': self,
      'spell': self.properties,
      'map': battle_map,
    }]

  @staticmethod
  def apply(battle, item, session=None):
    if item.get('type') != 'web':
      return

    if battle and session is None:
      session = battle.session
    if session is None:
      return

    source = item['source']
    battle_map = item.get('map') or battle.map_for(source)
    squares = [tuple(s) for s in item.get('squares', [])]
    effect = item.get('effect')

    zone = WebZone(source, battle, battle_map, squares, effect)
    register_persistent_zone(zone, battle)

    if effect is not None:
      source.add_casted_effect({
        'target': zone,
        'effect': effect,
        'expiration': session.game_time + int(item.get('spell', {}).get('duration_seconds', 3600)),
      })
      if battle is not None and hasattr(battle, 'start_concentration'):
        battle.start_concentration(source, effect)
      else:
        source.concentration_on(effect)

    affected = set()
    for x, y in squares:
      for target in battle_map.entities_at(x, y):
        uid = target.entity_uid
        if uid in affected:
          continue
        affected.add(uid)
        zone.apply_save(target, reason='cast')

    session.event_manager.received_event({
      'event': 'web',
      'source': source,
      'target': item.get('target'),
      'squares': item.get('squares', []),
    })
