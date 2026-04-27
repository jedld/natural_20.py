"""Light cantrip — touch one object/creature; it sheds bright + dim light.

5e text (paraphrased):
    Cantrip, 1 Action, Touch, V/M, 1 Hour, Evocation.
    You touch one object that is no larger than 10 feet in any dimension.
    Until the spell ends, the object sheds bright light in a 20-foot radius
    and dim light for an additional 20 feet. The light can be colored as
    you like. Completely covering the object with something opaque blocks
    the light. The spell ends if you cast it again or dismiss it as an
    action.

    If you target an object held or worn by a hostile creature, that
    creature must succeed on a Dexterity saving throw to avoid the spell.

Implementation notes:
- The target is a creature/entity (representing either the creature itself
  or an item it carries). Light is realised by registering a
  ``light_override`` effect on the target — the same mechanism used by
  Guiding Bolt — so the static lighting builder picks it up automatically.
- Hostility (relative to the caster) is determined via
  ``battle.opposing``. Hostile targets must fail a Dexterity save against
  the caster's spell save DC for the spell to take effect.
- Recasting this spell ends any prior Light created by the same caster
  (only one active Light per caster), matching the spell's duration rule.
"""

from natural20.spell.spell import Spell


class LightEffect:
    """Represents an active Light cantrip on a target.

    Stored in the caster's ``casted_effects`` and registered on the target
    as a ``light_override`` effect handler. Removing the effect from the
    caster (e.g. ``source.remove_effect('light')``) triggers ``dismiss``
    which strips the ``light_override`` entry from the target.
    """

    def __init__(self, source, target, color='white', duration_seconds=3600):
        self.source = source
        self.target = target
        self.color = color
        self.duration = duration_seconds
        # Set when the spell is cast through a SpellAction so dismiss hooks
        # have a back-reference if needed.
        self.action = None

    @property
    def id(self):
        return 'light'

    def __str__(self):
        return f'Light ({self.color})'

    def dismiss(self, entity, effect, opts=None):
        """Strip the light_override registration from the target.

        Called by ``Entity.remove_effect`` on the caster. We avoid calling
        ``target.remove_effect`` here to prevent a recursive dismissal of
        the same effect instance — instead we manually rebuild the
        target's effects map without entries pointing at this LightEffect.
        """
        target = self.target
        if target is None:
            return

        new_effects = {}
        for key, value in getattr(target, 'effects', {}).items():
            new_effects[key] = [f for f in value if f.get('effect') is not self]
        target.effects = new_effects

        # Also drop any event hooks we registered on the target (none today,
        # but kept symmetric in case future versions hook events).
        new_hooks = {}
        for key, value in getattr(target, 'entity_event_hooks', {}).items():
            new_hooks[key] = [f for f in value if f.get('effect') is not self]
        target.entity_event_hooks = new_hooks


class LightSpell(Spell):
    # Default radii (feet) per the 5e Light cantrip.
    BRIGHT_FEET = 20
    DIM_FEET = 20

    # ------------------------------------------------------------------ #
    # Targeting
    # ------------------------------------------------------------------ #
    def build_map(self, orig_action):
        def set_target(target):
            if not target:
                raise ValueError("Invalid target")
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    # 5 ft = touch. The 20-ft "*" in some compendiums refers
                    # to extended reach via spellcasting focus rules, which
                    # are out of scope here.
                    'range': self.properties.get('range', 5),
                    'target_types': ['allies', 'self', 'enemies'],
                },
            ],
            'next': set_target,
        }

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def validate(self, battle_map, target=None):
        self.errors = []
        if target is None:
            target = self.target

        if target is None:
            self.errors.append("target required")
            return False

        max_range = self.properties.get('range', 5)
        if isinstance(max_range, str):
            # YAML might say "touch"; treat as 5 ft.
            max_range = 5

        if battle_map is not None and self.source is not None:
            distance_feet = battle_map.distance(self.source, target) * battle_map.feet_per_grid
            if distance_feet > max_range:
                self.errors.append("target out of range")

        return len(self.errors) == 0

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #
    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        color = self.properties.get('color', 'white')

        save_required = False
        if battle is not None and target is not None and target is not entity:
            try:
                save_required = battle.opposing(entity, target)
            except Exception:
                save_required = False

        item = {
            'type': 'light',
            'source': entity,
            'target': target,
            'color': color,
            'effect': LightEffect(entity, target, color=color),
            'spell': self.properties,
        }

        if save_required:
            saving_throw = target.save_throw('dexterity', battle, {'is_magical': True})
            ability = self._caster_spell_ability(entity)
            try:
                dc = entity.spell_save_dc(ability)
            except Exception:
                dc = entity.spell_save_dc()
            item['saving_throw'] = saving_throw
            item['save_dc'] = dc
            item['save_success'] = saving_throw.result() >= dc
        else:
            item['saving_throw'] = None
            item['save_success'] = False  # i.e., no save needed; spell hits

        return [item]

    @staticmethod
    def _caster_spell_ability(entity):
        # Best-effort: prefer the caster's class spell ability if available.
        for attr in ('spell_ability', 'spellcasting_ability'):
            getter = getattr(entity, attr, None)
            if callable(getter):
                try:
                    val = getter()
                    if val:
                        return val
                except Exception:
                    pass
        return 'intelligence'

    # ------------------------------------------------------------------ #
    # light_override handler — invoked by Entity.eval_effect via the
    # static_light_builder. Returns the (possibly augmented) light bubble.
    # ------------------------------------------------------------------ #
    @staticmethod
    def light_override(entity, opt=None):
        opt = opt or {}
        cur_bright = opt.get('bright', 0) or 0
        cur_dim = opt.get('dim', 0) or 0
        return {
            'bright': max(cur_bright, LightSpell.BRIGHT_FEET),
            'dim': max(cur_dim, LightSpell.DIM_FEET),
        }

    # ------------------------------------------------------------------ #
    # Apply
    # ------------------------------------------------------------------ #
    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'light':
            return

        if battle is not None and session is None:
            session = battle.session

        source = item['source']
        target = item['target']

        # End any previous Light this caster has active — only one Light
        # per caster (per the spell's "ends if you cast it again" clause).
        try:
            source.remove_effect('light')
        except Exception:
            pass

        # If the target was a hostile creature and they made the save, the
        # spell fizzles entirely.
        if item.get('saving_throw') is not None and item.get('save_success'):
            if session is not None:
                session.event_manager.received_event({
                    'event': 'light',
                    'spell': item.get('effect'),
                    'source': source,
                    'target': target,
                    'success': True,        # i.e., target saved
                    'roll': item.get('saving_throw'),
                    'save_dc': item.get('save_dc'),
                })
            return

        effect = item['effect']
        # Make sure the effect knows its target (build_map/resolve already
        # set source/target, but reaffirm for safety).
        effect.target = target
        effect.source = source

        duration = effect.duration  # seconds (3600 for 1 hour)

        source.add_casted_effect({
            'target': target,
            'effect': effect,
            'expiration': session.game_time + duration if session is not None else None,
        })

        target.register_effect(
            'light_override',
            LightSpell,
            effect=effect,
            source=source,
            duration=duration,
        )

        if session is not None:
            session.event_manager.received_event({
                'event': 'light',
                'spell': effect,
                'source': source,
                'target': target,
                'color': effect.color,
                'success': False,        # i.e., spell took effect
                'roll': item.get('saving_throw'),
                'save_dc': item.get('save_dc'),
            })
