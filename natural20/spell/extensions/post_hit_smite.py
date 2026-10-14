"""Smite spells cast as a Bonus Action right after a melee hit (SRD 5.2 pattern).

Searing Smite, Shining Smite and similar spells share the same trigger:
"Bonus Action, which you take immediately after hitting a target with a Melee
weapon or an Unarmed Strike". ``PostHitSmiteOffer`` is registered as an
``on_attack_hit`` hook on the caster (see ``Paladin.initialize_paladin``) and
offers one ``PostHitSmiteAction`` per usable spell slot (slot level >= the
spell's level). The chosen action rolls the extra damage (dice doubled on a
critical hit), spends the slot and the bonus action, and returns result items:
a ``spell_damage`` item plus whatever rider items the subclass adds.

Subclasses set:

* ``SPELL_ID`` — YAML key of the spell (must be prepared).
* ``ACTION_CLASS`` — the ``PostHitSmiteAction`` subclass to offer.
* ``REQUIRED_RULESET`` — ruleset name the offer is limited to, or ``None``.
"""
from __future__ import annotations

from natural20.action import Action, AsyncReactionHandler
from natural20.die_roll import DieRoll
from natural20.spell.spell import consume_resource


class PostHitSmiteAction(Action):
    """Apply a smite spell after a confirmed melee hit (bonus action)."""

    SPELL_ID = None
    DAMAGE_DIE = 'd6'
    BASE_DICE = 1
    DICE_PER_SLOT = 1
    DAMAGE_TYPE = None
    CASTING_CLASS = 'paladin'

    def __init__(self, session, source, target, slot_level, spell_details, attack_result):
        super().__init__(session, source, self.SPELL_ID)
        self.target = target
        self.spell_details = spell_details or {}
        self.slot_level = int(slot_level or self.spell_level())
        self.attack_result = attack_result or {}
        self.as_bonus_action = True

    def spell_level(self):
        return int((self.spell_details or {}).get('level') or 1)

    def spell_label(self):
        return self.spell_details.get('label') or self.spell_details.get('name') or str(self.SPELL_ID)

    def label(self):
        return f"{self.spell_label()} (Level {self.slot_level})"

    def button_label(self):
        return self.label()

    def name(self):
        return self.label()

    def damage_dice_count(self):
        return self.BASE_DICE + self.DICE_PER_SLOT * max(0, self.slot_level - self.spell_level())

    def damage_type(self):
        return self.DAMAGE_TYPE or self.spell_details.get('damage_type')

    def rider_items(self, battle, damage_roll):
        """Extra result items applied after the damage (ongoing effects)."""
        return []

    def resolve(self, session, map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        attack_roll = self.attack_result.get('attack_roll')
        is_crit = bool(attack_roll is not None and attack_roll.nat_20())
        damage_roll = DieRoll.roll(
            f'{self.damage_dice_count()}{self.DAMAGE_DIE}',
            crit=is_crit,
            battle=battle,
            entity=self.source,
            description=f'dice_roll.spells.{self.SPELL_ID}',
        )
        consume_resource(
            battle,
            self.source,
            self.spell_details,
            cast_level=self.slot_level,
            casting_class=self.CASTING_CLASS,
        )
        if battle is not None:
            state = battle.entity_state_for(self.source)
            if state is not None and state.get('bonus_action', 0) > 0:
                state['bonus_action'] -= 1

        self.result = [
            {
                'type': 'spell_damage',
                'source': self.source,
                'target': self.target,
                'attack_name': self.spell_details.get('name', self.spell_label()),
                'damage_type': self.damage_type(),
                'damage_roll': damage_roll,
                'damage': damage_roll,
                'attack_roll': attack_roll,
                'spell': self.spell_details,
                'cast_level': self.slot_level,
                'trigger': self.SPELL_ID,
            },
        ] + list(self.rider_items(battle, damage_roll) or [])
        return self


class PostHitSmiteOffer:
    """``on_attack_hit`` hook offering a smite spell as a post-hit bonus action."""

    SPELL_ID = None
    ACTION_CLASS = PostHitSmiteAction
    REQUIRED_RULESET = None
    CASTING_CLASS = 'paladin'

    def __init__(self, owner):
        self.owner = owner

    def __str__(self):
        return str(self.SPELL_ID)

    def _ruleset_allows(self, entity):
        if not self.REQUIRED_RULESET:
            return True
        session = getattr(entity, 'session', None)
        ruleset = getattr(session, 'ruleset', None) if session else None
        return bool(ruleset and ruleset.name == self.REQUIRED_RULESET)

    @staticmethod
    def _is_melee_hit(entity, hit_result):
        if hit_result.get('thrown'):
            return False
        weapon_key = hit_result.get('weapon')
        weapon_meta = hit_result.get('npc_action')
        if not weapon_meta and weapon_key:
            weapon_meta = entity.session.load_weapon(weapon_key)
        return bool(weapon_meta) and weapon_meta.get('type') == 'melee_attack'

    def available_slot_levels(self, entity, spell_level):
        slot_owner = entity.owner if entity.familiar() else entity
        slots = getattr(slot_owner, 'spell_slots', {}).get(self.CASTING_CLASS, {})
        return [lvl for lvl, qty in sorted(slots.items())
                if lvl > 0 and lvl >= spell_level and qty > 0]

    def on_attack_hit(self, entity, opts=None):
        opts = opts or {}
        if entity != self.owner:
            return []
        if not self._ruleset_allows(entity):
            return []

        prepared = entity.prepared_spells() or [] if hasattr(entity, 'prepared_spells') else []
        if self.SPELL_ID not in prepared:
            return []

        hit_result = opts.get('result') or {}
        if not hit_result.get('hit?'):
            return []
        battle = hit_result.get('battle')
        target = hit_result.get('target')
        if battle is None or target is None:
            return []
        if entity.total_bonus_actions(battle) <= 0:
            return []
        if not self._is_melee_hit(entity, hit_result):
            return []

        try:
            spell_details = entity.session.load_spell(self.SPELL_ID)
        except Exception:
            spell_details = None
        if not spell_details:
            return []
        available = self.available_slot_levels(entity, int(spell_details.get('level') or 1))
        if not available:
            return []

        valid_actions = [
            self.ACTION_CLASS(entity.session, entity, target, lvl, spell_details, hit_result)
            for lvl in available
        ]

        stored_reaction = opts.get('stored_reaction')
        attack_action = opts.get('action')
        controller = battle.controller_for(entity)
        if stored_reaction not in (None, False):
            selected = stored_reaction
        elif controller is None:
            selected = valid_actions[0]
        else:
            selected = controller.select_reaction(
                entity, battle, battle.map_for(entity), valid_actions,
                {
                    'type': self.SPELL_ID,
                    'trigger': 'on_attack_hit',
                    'source': entity,
                    'target': target,
                    'result': hit_result,
                    'spell': spell_details,
                },
            )

        if hasattr(selected, 'send'):
            raise AsyncReactionHandler(entity, selected, attack_action, 'on_attack_hit')
        if not selected:
            return []
        if isinstance(selected, int) and 0 <= selected < len(valid_actions):
            selected = valid_actions[selected]
        if not isinstance(selected, self.ACTION_CLASS):
            return []
        resolved = selected.resolve(entity.session, battle.map_for(entity), {'battle': battle})
        return resolved.result if resolved.result else []
