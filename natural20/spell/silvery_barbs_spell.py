"""Silvery Barbs (Strixhaven) — 1st-level enchantment, reaction.

When a creature you can see within 60 feet succeeds on an attack roll, an
ability check, or a saving throw, you can use your reaction to force that
creature to reroll and use the lower result. You also choose another creature
you can see within 60 feet; the chosen creature has advantage on its next
attack roll, ability check, or saving throw within 1 minute.
"""

import copy

from natural20.action import AsyncReactionHandler
from natural20.die_roll import DieRoll, DieRolls
from natural20.spell.spell import Spell


class SilveryBarbsAdvantageEffect:
    """One-shot advantage on the next attack roll, ability check, or save."""

    def __init__(self, source, ally):
        self.source = source
        self.target = ally
        self.action = None
        self.id = f"silvery_barbs_advantage:{id(self)}"

    def __str__(self):
        return 'silvery_barbs'

    @staticmethod
    def _dismiss_after_use(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        return [{
            'type': 'dismiss_effect',
            'source': effect.source,
            'target': entity,
            'effect': effect,
        }]

    @staticmethod
    def attack_advantage_modifier(entity, opt=None):
        return [['silvery_barbs_advantage'], []]

    @staticmethod
    def save_advantage_modifier(entity, opt=None):
        return [['silvery_barbs_advantage'], []]

    @staticmethod
    def ability_check_advantage_modifier(entity, opt=None):
        return [['silvery_barbs_advantage'], []]

    @staticmethod
    def attack_resolved(entity, opt=None):
        return SilveryBarbsAdvantageEffect._dismiss_after_use(entity, opt)

    @staticmethod
    def save_resolved(entity, opt=None):
        return SilveryBarbsAdvantageEffect._dismiss_after_use(entity, opt)

    @staticmethod
    def ability_check_resolved(entity, opt=None):
        return SilveryBarbsAdvantageEffect._dismiss_after_use(entity, opt)


class SilveryBarbsSpell(Spell):
    """Silvery Barbs spell."""

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
                    'range': self.properties.get('range', 60),
                    'target_types': ['allies'],
                },
            ],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        ally = spell_action.target
        return [{
            'type': 'silvery_barbs_advantage',
            'source': entity,
            'target': ally,
            'spell': self.properties,
            'effect': self,
        }]

    @staticmethod
    def _primary_attack_die_roll(attack_roll):
        if isinstance(attack_roll, DieRolls):
            for roll in attack_roll.rolls:
                if isinstance(roll, DieRoll) and roll.die_sides == 20:
                    return roll
            return attack_roll.rolls[0] if attack_roll.rolls else None
        if isinstance(attack_roll, DieRoll) and attack_roll.die_sides == 20:
            return attack_roll
        return None

    @staticmethod
    def _d20_face(die_roll):
        if die_roll is None or not getattr(die_roll, 'rolls', None):
            return None
        if die_roll.advantage or die_roll.disadvantage:
            faces = die_roll.rolls[0]
            if isinstance(faces, (tuple, list)):
                return min(faces) if die_roll.disadvantage else max(faces)
            return faces
        return die_roll.rolls[0]

    @staticmethod
    def _attack_modifier(die_roll):
        if die_roll is None:
            return 0
        return getattr(die_roll, 'modifier', 0)

    @staticmethod
    def _apply_lower_d20_reroll(original_action, attack_roll, battle, attacker):
        """Reroll the attack d20 and keep the lower face (modifiers unchanged)."""
        base = SilveryBarbsSpell._primary_attack_die_roll(attack_roll)
        if base is None:
            return attack_roll, None, False

        modifier = SilveryBarbsSpell._attack_modifier(base)
        new_d20_roll = DieRoll.roll(
            f'1d20{"+" if modifier >= 0 else ""}{modifier}',
            description='dice_roll.silvery_barbs',
            entity=attacker,
            battle=battle,
        )

        old_face = SilveryBarbsSpell._d20_face(base)
        new_face = SilveryBarbsSpell._d20_face(new_d20_roll)
        if old_face is None or new_face is None:
            return attack_roll, new_d20_roll, False

        chosen_face = min(old_face, new_face)
        replaced = chosen_face < old_face

        replacement = DieRoll(
            [chosen_face],
            modifier,
            die_sides=20,
            advantage=False,
            disadvantage=False,
            description='dice_roll.silvery_barbs',
        )
        replacement.metadata = copy.copy(getattr(base, 'metadata', {}))

        if isinstance(attack_roll, DieRolls):
            updated_rolls = []
            replaced_primary = False
            for roll in attack_roll.rolls:
                if (
                    not replaced_primary
                    and isinstance(roll, DieRoll)
                    and roll.die_sides == 20
                ):
                    updated_rolls.append(replacement)
                    replaced_primary = True
                else:
                    updated_rolls.append(roll)
            updated = DieRolls(updated_rolls)
        else:
            updated = replacement

        if original_action is not None and hasattr(original_action, 'attack_roll'):
            original_action.attack_roll = updated
        return updated, new_d20_roll, replaced

    @staticmethod
    def _dismiss_existing_advantage_buffs(ally):
        for entries in list(getattr(ally, 'effects', {}).values()):
            for entry in list(entries):
                effect = entry.get('effect')
                if isinstance(effect, SilveryBarbsAdvantageEffect):
                    ally.dismiss_effect(effect)

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'silvery_barbs_advantage':
            ally = item['target']
            source = item['source']
            SilveryBarbsSpell._dismiss_existing_advantage_buffs(ally)
            buff = SilveryBarbsAdvantageEffect(source, ally)
            buff.action = item.get('effect').action if item.get('effect') else None
            duration = 60
            ally.register_effect(
                'attack_advantage_modifier',
                SilveryBarbsAdvantageEffect,
                effect=buff,
                source=source,
                duration=duration,
            )
            ally.register_effect(
                'save_advantage_modifier',
                SilveryBarbsAdvantageEffect,
                effect=buff,
                source=source,
                duration=duration,
            )
            ally.register_effect(
                'ability_check_advantage_modifier',
                SilveryBarbsAdvantageEffect,
                effect=buff,
                source=source,
                duration=duration,
            )
            for hook in ('attack_resolved', 'save_resolved', 'ability_check_resolved'):
                ally.register_event_hook(
                    hook,
                    SilveryBarbsAdvantageEffect,
                    effect=buff,
                    source=source,
                    duration=duration,
                )
            if session is None and battle is not None:
                session = battle.session
            if session is not None:
                spell_label = item.get('spell', {}).get('label', 'Silvery Barbs')
                session.event_manager.received_event({
                    'event': 'silvery_barbs_advantage',
                    'source': source,
                    'target': ally,
                    'spell_label': spell_label,
                })
        elif item['type'] == 'silvery_barbs_reroll':
            session = session or (battle.session if battle else None)
            if session is not None:
                spell_label = item.get('spell', {}).get('label', 'Silvery Barbs')
                session.event_manager.received_event({
                    'event': 'silvery_barbs_reroll',
                    'source': item['source'],
                    'target': item['target'],
                    'old_roll': item.get('old_roll'),
                    'new_roll': item.get('new_roll'),
                    'replaced': item.get('replaced', False),
                    'spell_label': spell_label,
                })

    @staticmethod
    def after_attack_roll(battle, entity, attacker, attack_roll, effective_ac, opts=None):
        if opts is None:
            opts = {}
        if battle is None or attack_roll is None:
            return [[], False]
        if entity is attacker:
            return [[], False]
        if attack_roll.nat_1():
            return [[], False]
        if not attack_roll.nat_20() and attack_roll.result() < effective_ac:
            return [[], False]

        spell_details = battle.session.load_spell('silvery_barbs')
        if spell_details is None:
            return [[], False]

        if not entity.conscious() or not entity.has_reaction(battle):
            return [[], False]

        from natural20.actions.spell_action import SpellAction
        if not SpellAction.can_cast(entity, battle, 'silvery_barbs'):
            return [[], False]

        bmap = battle.map_for(entity) if battle else None
        if bmap is None:
            return [[], False]
        try:
            distance_ft = bmap.distance(entity, attacker) * 5
        except Exception:
            return [[], False]
        if distance_ft > spell_details.get('range', 60):
            return [[], False]
        try:
            if not bmap.can_see(entity, attacker):
                return [[], False]
        except Exception:
            return [[], False]

        action = SpellAction(battle.session, entity, 'spell')
        action.spell = spell_details
        action.level = spell_details.get('level', 1)
        action.at_level = action.level
        action.spell_class = SilveryBarbsSpell
        spell_instance = SilveryBarbsSpell(
            battle.session, entity, 'SilveryBarbsSpell', spell_details
        )
        spell_instance.action = action
        action.spell_action = spell_instance
        action.target = attacker

        slot_owner = entity.owner if entity.familiar() else entity
        if hasattr(slot_owner, 'next_spell_slot_level'):
            for klass in spell_details.get('spell_list_classes', []):
                slot_level = slot_owner.next_spell_slot_level(klass.lower(), action.at_level)
                if slot_level is not None:
                    action.at_level = slot_level
                    action.spellcasting_class = klass.lower()
                    break

        controller = battle.controller_for(entity)
        if controller is None:
            return [[], False]

        original_action = opts.get('original_action')
        event_payload = {
            'type': 'silvery_barbs',
            'trigger': 'silvery_barbs',
            'source': entity,
            'target': attacker,
            'attacker': attacker,
            'attack_roll': attack_roll,
            'spell': spell_details,
            'effect': spell_instance,
        }

        if original_action is not None:
            stored = original_action.has_async_reaction_for_source(entity, 'silvery_barbs')
            if stored is not False:
                chosen = stored
            else:
                chosen = controller.select_reaction(
                    entity, battle, bmap, [action], event_payload,
                )
        else:
            chosen = controller.select_reaction(
                entity, battle, bmap, [action], event_payload,
            )

        if hasattr(chosen, 'send'):
            raise AsyncReactionHandler(entity, chosen, original_action, 'silvery_barbs')
        if not chosen:
            return [[], False]

        updated_roll, new_d20_roll, replaced = SilveryBarbsSpell._apply_lower_d20_reroll(
            original_action, attack_roll, battle, attacker,
        )
        ally = SilveryBarbsSpell._pick_ally(battle, entity, attacker, bmap, spell_details)
        spell_instance.consume(battle)

        events = [{
            'type': 'silvery_barbs_reroll',
            'source': entity,
            'target': attacker,
            'old_roll': attack_roll,
            'new_roll': new_d20_roll,
            'replaced': replaced,
            'spell': spell_details,
            'effect': spell_instance,
        }]
        if ally is not None:
            events.append({
                'type': 'silvery_barbs_advantage',
                'source': entity,
                'target': ally,
                'spell': spell_details,
                'effect': spell_instance,
            })

        return [events, False]

    @staticmethod
    def _pick_ally(battle, caster, attacker, bmap, spell_details):
        """Pick an ally within range and line of sight of the caster."""
        spell_range = spell_details.get('range', 60)
        candidates = []
        try:
            allies = battle.allies_of(caster) if hasattr(battle, 'allies_of') else []
            for other in list(battle.entities.keys()):
                if other is attacker or not other.conscious():
                    continue
                if other is not caster and other not in allies:
                    continue
                try:
                    dist = bmap.distance(caster, other) * 5
                except Exception:
                    continue
                if dist > spell_range:
                    continue
                try:
                    if not bmap.can_see(caster, other):
                        continue
                except Exception:
                    continue
                candidates.append((0 if other is not caster else 1, dist, other))
        except Exception:
            return caster
        if not candidates:
            return caster
        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates[0][2]
