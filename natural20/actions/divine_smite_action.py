from __future__ import annotations

from typing import Any, Dict, Optional

from natural20.action import Action
from natural20.die_roll import DieRoll
from natural20.spell.spell import consume_resource
from natural20.actions.spell_action import SpellAction


class DivineSmiteAction(Action):
    """Apply Divine Smite extra radiant damage after a melee hit."""

    def __init__(
        self,
        session,
        source,
        target,
        slot_level: int,
        spell_details: Dict[str, Any],
        attack_result: Dict[str, Any],
    ) -> None:
        super().__init__(session, source, 'divine_smite')
        self.target = target
        self.slot_level = slot_level
        self.spell_details = spell_details
        self.attack_result = attack_result

    def label(self) -> str:
        return f"Divine Smite (Level {self.slot_level})"

    def button_label(self) -> Optional[str]:
        return self.label()

    def name(self) -> str:
        return self.label()

    def compute_hit_probability(self, battle, opts=None):
        # Triggered after a confirmed hit.
        return 1.0

    def avg_damage(self, battle, opts=None):
        base_dice = self._damage_dice_count()
        return base_dice * 4.5

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        battle = opts.get('battle')

        damage_dice = self._damage_dice_count()

        # Per the standard 5e crit rule, "if an attack involves other damage
        # dice ... double those dice as well."  Divine Smite damage dice are
        # therefore doubled when the triggering melee attack was a crit.
        attack_roll = (self.attack_result or {}).get('attack_roll')
        is_crit = bool(attack_roll is not None and attack_roll.nat_20())

        roll_expression = f"{damage_dice}d8"
        damage_roll = DieRoll.roll(
            roll_expression,
            crit=is_crit,
            battle=battle,
            entity=self.source,
            description='dice_roll.spells.divine_smite'
        )

        consume_resource(
            battle,
            self.source,
            self.spell_details,
            cast_level=self.slot_level,
            casting_class='paladin'
        )

        session.event_manager.received_event({
            'event': 'divine_smite_cast',
            'source': self.source,
            'target': self.target,
            'slot_level': self.slot_level,
            'spell': self.spell_details
        })

        self.result = [{
            'type': 'spell_damage',
            'source': self.source,
            'target': self.target,
            'attack_name': self.spell_details.get('name', 'Divine Smite'),
            'damage_type': self.spell_details.get('damage_type', 'radiant'),
            'damage_roll': damage_roll,
            'damage': damage_roll,
            'attack_roll': self.attack_result.get('attack_roll') if self.attack_result else None,
            'spell': self.spell_details,
            'cast_level': self.slot_level,
            'trigger': 'divine_smite'
        }]

        return self

    # Maximum smite dice per RAW: 5d8 from a 4th+ level slot, +1d8 vs
    # undead or fiend (capping at 6d8 total).
    _MAX_BASE_DICE = 5

    def _damage_dice_count(self) -> int:
        base_dice = 2 + max(0, self.slot_level - 1)
        base_dice = min(base_dice, self._MAX_BASE_DICE)
        if self._is_fiend_or_undead(self.target):
            base_dice += 1
        return base_dice

    @staticmethod
    def _is_fiend_or_undead(target) -> bool:
        if target is None:
            return False
        race_tags = []
        if hasattr(target, 'properties'):
            race = target.properties.get('race', []) or []
            if isinstance(race, str):
                race_tags = [race.lower()]
            else:
                race_tags = [str(tag).lower() for tag in race]
        if hasattr(target, 'undead') and target.undead():
            return True
        return 'fiend' in race_tags or 'undead' in race_tags

    @staticmethod
    def apply(battle, item, session=None):
        return SpellAction.apply(battle, item, session)
