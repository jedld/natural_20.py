# Barbarian class mixin (D&D 5e SRD 2014, levels 1-2 only)
#
# Implements:
#   * Level 1 - Rage (bonus action; resistance to bludg/pierce/slash, +rage
#     damage on STR melee weapon attacks, advantage on STR checks/saves
#     while raging; 2 uses per long rest at L1-2; 1-minute / 10-round
#     duration; ends early if knocked unconscious).
#   * Level 1 - Unarmored Defense (Barbarian): AC = 10 + DEX + CON when
#     wearing no armor (shield allowed).
#   * Level 2 - Reckless Attack (toggle for the turn: advantage on STR
#     melee weapon attack rolls; attacks against the barbarian have
#     advantage until the start of the next turn).
#   * Level 2 - Danger Sense (advantage on DEX saves vs. effects you can
#     see; flag-only - exposed via class_feature for callers to consult).


# Rage uses by barbarian level (per SRD).
RAGE_USES = [
  2,   # 1
  2,   # 2
  3,   # 3
  3,   # 4
  3,   # 5
  4,   # 6
  4,   # 7
  4,   # 8
  4,   # 9
  4,   # 10
  4,   # 11
  5,   # 12
  5,   # 13
  5,   # 14
  5,   # 15
  5,   # 16
  6,   # 17
  6,   # 18
  6,   # 19
  None,  # 20 = unlimited (cap at 999 for resource accounting)
]


# Rage damage bonus by barbarian level (per SRD).
RAGE_DAMAGE = [
  2,  # 1
  2,  # 2
  2,  # 3
  2,  # 4
  2,  # 5
  2,  # 6
  2,  # 7
  2,  # 8
  3,  # 9
  3,  # 10
  3,  # 11
  3,  # 12
  3,  # 13
  3,  # 14
  3,  # 15
  3,  # 16
  4,  # 17
  4,  # 18
  4,  # 19
  4,  # 20
]


RAGE_DURATION_ROUNDS = 10  # 1 minute


class _BarbarianStartOfTurnHook:
  """Callable wrapper registered as a start_of_turn entity hook.

  Counts down rage duration and clears the per-turn Reckless Attack flag.
  Defined as a class so it survives entity-level cleanup code that
  inspects ``handler.method``.
  """

  def start_of_turn(self, entity, _opts=None):
    # Reckless Attack only lasts until the start of your next turn.
    setattr(entity, 'reckless_attack_active', False)

    if getattr(entity, 'raging', False):
      remaining = max(0, (entity.rage_rounds_remaining or 0) - 1)
      entity.rage_rounds_remaining = remaining
      if remaining <= 0:
        entity.end_rage(reason='duration')
    return []


class Barbarian:
  def initialize_barbarian(self):
    if getattr(self, 'rage_count', None) is None:
      self.rage_count = self._rage_max()
    self.rage_max = self._rage_max()
    if not hasattr(self, 'raging'):
      self.raging = False
    if not hasattr(self, 'rage_rounds_remaining'):
      self.rage_rounds_remaining = 0
    if not hasattr(self, 'reckless_attack_active'):
      self.reckless_attack_active = False
    # Register a per-turn cleanup hook (rage countdown + reckless reset).
    # entity_event_hooks are not persisted across save/load, but
    # initialize_barbarian is re-run by PlayerCharacter.__init__ on load,
    # so the hook is always present on a live instance.
    hook = _BarbarianStartOfTurnHook()
    self.register_event_hook('start_of_turn', hook, 'start_of_turn')

  # ---------------- Rage ----------------

  def _rage_max(self):
    if not getattr(self, 'barbarian_level', 0):
      return 0
    idx = max(1, min(self.barbarian_level, len(RAGE_USES))) - 1
    uses = RAGE_USES[idx]
    return 999 if uses is None else uses

  def rage_damage_bonus(self):
    if not getattr(self, 'barbarian_level', 0):
      return 0
    idx = max(1, min(self.barbarian_level, len(RAGE_DAMAGE))) - 1
    return RAGE_DAMAGE[idx]

  def has_rage(self, qty=1):
    return (self.rage_count or 0) >= qty

  def consume_rage(self, qty=1):
    self.rage_count = max(0, (self.rage_count or 0) - qty)

  def is_raging(self):
    return bool(getattr(self, 'raging', False))

  def begin_rage(self):
    """Enter rage. Caller is expected to have consumed action economy."""
    if self.raging:
      return
    self.consume_rage(1)
    self.raging = True
    self.rage_rounds_remaining = RAGE_DURATION_ROUNDS

  def end_rage(self, reason=None):
    if not self.raging:
      return
    self.raging = False
    self.rage_rounds_remaining = 0
    if hasattr(self, 'event_manager') and self.event_manager is not None:
      self.event_manager.received_event({
        'source': self,
        'event': 'rage_end',
        'reason': reason,
      })

  # ---------------- Reckless Attack ----------------

  def use_reckless_attack(self):
    self.reckless_attack_active = True

  def is_reckless(self):
    return bool(getattr(self, 'reckless_attack_active', False))

  # ---------------- Action discovery ----------------

  def special_actions_for_barbarian(self, session, battle):
    # Barbarian actions are surfaced via PlayerCharacter.ACTION_LIST; this
    # hook is left empty so the generic class iteration finds a valid
    # (no-op) entry point.
    return []

  # ---------------- Rest hooks ----------------

  def short_rest_for_barbarian(self, _battle):
    # Rage uses do not recharge on a short rest at low levels.
    return

  def long_rest_for_barbarian(self, _battle):
    self.rage_count = self._rage_max()
    self.rage_max = self._rage_max()
    # Rage ends if the barbarian rests.
    self.raging = False
    self.rage_rounds_remaining = 0
    self.reckless_attack_active = False
