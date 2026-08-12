"""Tempest Domain: Wrath of the Storm (Cleric L1, D&D 5e SRD).

When a creature within 5 feet of you that you can see hits you with an
attack, you can use your reaction to cause the creature to make a Dexterity
saving throw. The creature takes 2d8 lightning or thunder damage (your
choice) on a failed save, and half as much damage on a successful one.

You can use this feature a number of times equal to your Wisdom modifier
(minimum of once). You regain all expended uses when you finish a long rest.
"""

from __future__ import annotations

from natural20.action import Action
from natural20.die_roll import DieRoll
from natural20.utils.class_feature_registry import register_class_feature


class WrathOfTheStormAction(Action):
    """Reaction: thunderously rebuke a creature that hits you with an attack.

    This action is both:
    - A "ready" action the cleric can select on their turn (builds_map →
      resolve immediately) to declare they will use the reaction.
    - A reactive effect applied when the cleric is hit by a melee attack
      (via TempestWrathEffect), consuming a use and resolving the save.

    The feature is registered with the class-feature registry so it appears
    automatically in ``PlayerCharacter.available_actions`` for Tempest
    Domain clerics who have charges remaining.
    """

    # Default 2d8 at 1st level; each slot level above 1st adds 1d8.
    _DICE_PER_SLOT = 2

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.opts = opts or {}
        self.chosen_damage_type = self.opts.get('chosen_damage_type', 'lightning')

    def label(self):
        uses = getattr(self.source, 'wrath_of_the_storm_uses', 0)
        max_uses = getattr(self.source, 'wrath_of_the_storm_max', 1)
        return f"Wrath of the Storm ({uses}/{max_uses})"

    def __str__(self):
        return "WrathOfTheStorm"

    __repr__ = __str__

    @staticmethod
    def can(entity, battle, options=None):
        """Feature is available when the cleric has charges and a reaction (in combat)."""
        if not entity.class_feature('wrath_of_the_storm'):
            return False
        uses = getattr(entity, 'wrath_of_the_storm_uses', 0)
        if uses <= 0:
            return False
        if battle is not None:
            # In combat, requires a reaction available.
            if not entity.has_reaction(battle):
                return False
        return True

    def build_map(self):
        return self

    def resolve(self, session, battle_map, opts=None):
        battle = (opts or {}).get('battle')
        damage_dice = self._damage_dice_count()
        damage_roll = DieRoll.roll(
            f"{damage_dice}d8",
            battle=battle,
            entity=self.source,
            description='dice_roll.features.wrath_of_the_storm',
        )

        # Consume the reaction and one use of the feature.
        if battle:
            battle.consume(self.source, 'reaction')
        self._consume_use()

        session.event_manager.received_event({
            'source': self.source,
            'event': 'wrath_of_the_storm_ready',
            'damage_type': self.chosen_damage_type,
            'damage_dice': damage_dice,
        })

        self.result = [{
            'type': 'wrath_of_the_storm',
            'source': self.source,
            'damage_type': self.chosen_damage_type,
            'damage_roll': damage_roll,
            'damage': damage_roll,
            'damage_dice': damage_dice,
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        """Handle wrath_of_the_storm result items.

        In the "ready" flow (result from resolve() above), this records the
        pending reaction state on the cleric so the TempestWrathEffect can
        find the chosen damage type when the cleric is actually hit.
        """
        if item.get('type') != 'wrath_of_the_storm':
            return

        source = item['source']
        if session is None:
            session = battle.session if battle else None

        # Store chosen damage type on the entity for the reactive effect.
        source._wrath_chosen_damage_type = item.get('damage_type', 'lightning')
        source._wrath_damage_dice = item.get('damage_dice', 2)
        source._wrath_pending = True

        if battle:
            battle.event_manager.received_event({
                'source': source,
                'event': 'wrath_of_the_storm_ready',
                'damage_type': source._wrath_chosen_damage_type,
                'damage_dice': source._wrath_damage_dice,
            })

    def _damage_dice_count(self):
        """Return the number of d8 dice for Wrath of the Storm."""
        return self._DICE_PER_SLOT

    def _consume_use(self):
        """Decrement the feature's remaining uses."""
        current = getattr(self.source, 'wrath_of_the_storm_uses', 0)
        self.source.wrath_of_the_storm_uses = max(0, current - 1)

    @staticmethod
    def resolve_save_and_damage(session, source, target, battle, hit_result, damage_type_override=None):
        """Resolve the saving throw and damage for Wrath of the Storm.

        This is called by TempestWrathEffect when the cleric is hit by a
        melee attack and has a pending Wrath of the Storm.

        Args:
            session: Session instance.
            source: The cleric (source of the feature).
            target: The creature that attacked the cleric.
            battle: Battle instance (may be None).
            hit_result: Dict from the triggering attack (contains attack_roll, etc.).
            damage_type_override: Optional override for the damage type
                (lightning or thunder).

        Returns:
            List of damage event dicts, or empty list if the save succeeds.
        """
        if battle is None:
            session = battle.session if battle else None

        # Determine damage type: explicit > stored > default lightning.
        damage_type = (
            damage_type_override
            or getattr(source, '_wrath_chosen_damage_type', None)
            or 'lightning'
        )
        damage_type = str(damage_type).strip().lower()
        if damage_type not in ('lightning', 'thunder'):
            damage_type = 'lightning'

        damage_dice = getattr(source, '_wrath_damage_dice', 2)

        # Roll Dexterity saving throw for the attacker.
        save_roll = target.save_throw('dexterity', battle)
        spell_dc = source.spell_save_dc()
        save_success = save_roll.result() >= spell_dc

        # Roll damage.
        damage_roll = DieRoll.roll(
            f"{damage_dice}d8",
            crit=False,
            battle=battle,
            entity=source,
            description='dice_roll.features.wrath_of_the_storm',
        )

        # Consume the feature use.
        source._consume_use()

        # Clear pending state.
        source._wrath_pending = False
        source._wrath_chosen_damage_type = None
        source._wrath_damage_dice = 2

        damage_result = damage_roll.result()
        half_damage = damage_result // 2

        if save_success:
            damage_amount = half_damage
        else:
            damage_amount = damage_result

        damage_events = []
        if damage_amount > 0:
            damage_events.append({
                'source': source,
                'target': target,
                'attack_name': 'wrath_of_the_storm',
                'damage_type': damage_type,
                'damage_roll': damage_roll,
                'advantage_mod': 0,
                'adv_info': '',
                'damage': damage_amount,
                'damage_type_chosen': damage_type,
                'save_roll': save_roll,
                'save_dc': spell_dc,
                'save_success': save_success,
                'type': 'spell_damage',
            })

        # Emit battle log event.
        if battle:
            battle.event_manager.received_event({
                'source': source,
                'target': target,
                'event': 'wrath_of_the_storm',
                'damage_type': damage_type,
                'damage': damage_amount,
                'save_roll': save_roll.result(),
                'save_dc': spell_dc,
                'save_success': save_success,
                'hit_result': hit_result,
            })

        return damage_events


# Register the class feature so WrathOfTheStormAction is picked up
# by collect_class_feature_actions() in PlayerCharacter.available_actions.
register_class_feature(
    feature_id='wrath_of_the_storm',
    action_class=WrathOfTheStormAction,
    provides=lambda entity: entity.class_feature('wrath_of_the_storm')
    and getattr(entity, 'wrath_of_the_storm_uses', 0) > 0,
)
