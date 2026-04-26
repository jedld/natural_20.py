"""Silvery Barbs (Strixhaven) — 1st-level enchantment, reaction.

When a creature you can see within 60 feet succeeds on an attack roll, an
ability check, or a saving throw, you can use your reaction to force that
creature to reroll and use the lower result. You also choose another creature
you can see within 60 feet; the chosen creature has advantage on its next
attack roll, ability check, or saving throw within 1 minute.

This implementation focuses on the most common trigger — a successful attack
roll — and is invoked from
``natural20.utils.attack_util.after_attack_roll_hook`` for any third-party
creature within 60 feet of the attacker that has Silvery Barbs prepared and
still has a reaction and a 1st-level (or higher) spell slot available.
"""

from natural20.action import AsyncReactionHandler
from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


class SilveryBarbsAdvantageEffect:
    """One-shot ``attack_advantage_modifier`` effect for the chosen ally.

    Mirrors the True Strike pattern: hooks into ``attack_resolved`` so the
    effect dismisses itself the moment the ally rolls their next attack.
    """

    def __init__(self, source, ally):
        self.source = source
        self.target = ally  # mirror of effect "target" so dismiss_effect works
        self.action = None  # set by the spell when registered
        # ``remove_effect`` keys effects by ``id``; use a stable per-instance id.
        self.id = f"silvery_barbs_advantage:{id(self)}"

    @staticmethod
    def attack_advantage_modifier(entity, opt=None):
        return [['silvery_barbs_advantage'], []]

    @staticmethod
    def attack_resolved(entity, opt=None):
        # Fired on the ally right after they roll an attack — drop the buff.
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        return [{
            'type': 'dismiss_effect',
            'source': effect.source,
            'target': entity,
            'effect': effect,
        }]


class SilveryBarbsSpell(Spell):
    """Silvery Barbs spell.

    The reaction trigger lives in :meth:`after_attack_roll`. ``build_map`` is
    provided so the spell can also appear in a caster's normal action menu
    (e.g. for setup-only "advantage to ally" usage), but its primary
    integration point is the third-party reaction scan.
    """

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
    def apply(battle, item, session=None):
        if item['type'] == 'silvery_barbs_advantage':
            ally = item['target']
            source = item['source']
            buff = SilveryBarbsAdvantageEffect(source, ally)
            buff.action = item.get('effect').action if item.get('effect') else None
            ally.register_effect(
                'attack_advantage_modifier',
                SilveryBarbsAdvantageEffect,
                effect=buff,
                source=source,
                duration=60,  # 1 minute
            )
            ally.register_event_hook(
                'attack_resolved',
                SilveryBarbsAdvantageEffect,
                effect=buff,
                source=source,
                duration=60,
            )
            if session is None and battle is not None:
                session = battle.session
            if session is not None:
                session.event_manager.received_event({
                    'event': 'spell_buf',
                    'spell': item.get('effect'),
                    'source': source,
                    'target': ally,
                })
        elif item['type'] == 'silvery_barbs_reroll':
            session = session or (battle.session if battle else None)
            if session is not None:
                session.event_manager.received_event({
                    'event': 'silvery_barbs_reroll',
                    'source': item['source'],
                    'target': item['target'],
                    'old_roll': item.get('old_roll'),
                    'new_roll': item.get('new_roll'),
                })

    # ------------------------------------------------------------------ #
    # Reaction trigger (called from after_attack_roll_hook for every third
    # party that has Silvery Barbs prepared).
    # ------------------------------------------------------------------ #
    @staticmethod
    def after_attack_roll(battle, entity, attacker, attack_roll, effective_ac, opts=None):
        """Try to fire Silvery Barbs as a reaction.

        ``entity`` is the prospective Silvery Barbs caster (a third party).
        ``attacker`` is the creature that just rolled. The spell only fires
        when the attack succeeded (so the reroll has a chance to drop it
        below the AC).
        """
        if opts is None:
            opts = {}
        if battle is None or attack_roll is None:
            return [[], False]
        if entity is attacker:
            # Silvery Barbs targets a creature you can see; allow self-cast on
            # an attacker that is not the caster only.
            return [[], False]
        if attack_roll.nat_1():
            # Already a critical miss — nothing to do.
            return [[], False]
        # Only react to a successful attack roll. Nat 20 is included.
        if not attack_roll.nat_20() and attack_roll.result() < effective_ac:
            return [[], False]

        spell_details = battle.session.load_spell('silvery_barbs')
        if spell_details is None:
            return [[], False]

        # Resource gating ----------------------------------------------------
        if not entity.conscious() or not entity.has_reaction(battle):
            return [[], False]

        from natural20.actions.spell_action import SpellAction
        if not SpellAction.can_cast(entity, battle, 'silvery_barbs'):
            return [[], False]

        # Range + visibility -------------------------------------------------
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

        # Build inline SpellAction (mirrors Hellish Rebuke wiring) -----------
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

        # Resolve preferred slot level from caster's class list.
        slot_owner = entity.owner if entity.familiar() else entity
        if hasattr(slot_owner, 'next_spell_slot_level'):
            for klass in spell_details.get('spell_list_classes', []):
                slot_level = slot_owner.next_spell_slot_level(klass.lower(), action.at_level)
                if slot_level is not None:
                    action.at_level = slot_level
                    action.spellcasting_class = klass.lower()
                    break

        # Ask the controller --------------------------------------------------
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

        # ---- Force the reroll, take the lower result -----------------------
        new_roll = DieRoll.roll(
            f'1d20{"+" if attack_roll.modifier >= 0 else ""}{attack_roll.modifier}',
            description='dice_roll.silvery_barbs',
            entity=attacker,
            battle=battle,
        )

        old_total = attack_roll.result()
        new_total = new_roll.result()
        if new_total < old_total and original_action is not None and hasattr(original_action, 'attack_roll'):
            original_action.attack_roll = new_roll

        # ---- Pick an ally to receive advantage -----------------------------
        ally = SilveryBarbsSpell._pick_ally(battle, entity, attacker, bmap, spell_details)

        # ---- Consume reaction + slot ---------------------------------------
        spell_instance.consume(battle)

        events = [{
            'type': 'silvery_barbs_reroll',
            'source': entity,
            'target': attacker,
            'old_roll': attack_roll,
            'new_roll': new_roll,
            'replaced': new_total < old_total,
            'spell': spell_details,
            'effect': spell_instance,
        }]
        if ally is not None:
            adv_event = {
                'type': 'silvery_barbs_advantage',
                'source': entity,
                'target': ally,
                'spell': spell_details,
                'effect': spell_instance,
            }
            # Apply immediately so the buff is live before commit.
            SilveryBarbsSpell.apply(battle, adv_event, battle.session)
            events.append(adv_event)

        # Notify listeners.
        try:
            battle.session.event_manager.received_event({
                'event': 'silvery_barbs_reroll',
                'source': entity,
                'target': attacker,
                'old_roll': attack_roll,
                'new_roll': new_roll,
                'replaced': new_total < old_total,
            })
        except Exception:
            pass

        return [events, False]

    # ------------------------------------------------------------------ #
    @staticmethod
    def _pick_ally(battle, caster, attacker, bmap, spell_details):
        """Pick an ally within range and line of sight of the caster.

        Prefers an ally other than the caster; falls back to the caster.
        Returns ``None`` if no eligible ally is found.
        """
        spell_range = spell_details.get('range', 60)
        candidates = []
        try:
            for other in list(battle.entities.keys()):
                if other is attacker or not other.conscious():
                    continue
                # only allies of the caster (same group) are eligible
                if hasattr(battle, 'allies_of'):
                    allies = battle.allies_of(caster)
                else:
                    allies = []
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
