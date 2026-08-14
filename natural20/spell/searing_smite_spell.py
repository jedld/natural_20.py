"""Searing Smite — 1st-level paladin evocation (SRD 5.2). BA after melee hit; not concentration."""

from natural20.action import Action, AsyncReactionHandler
from natural20.die_roll import DieRoll
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell, consume_resource
from natural20.utils.attack_util import damage_event


class SearingSmiteAction(Action):
    """Apply Searing Smite after a confirmed melee hit (bonus action, 2024)."""

    def __init__(self, session, source, target, slot_level, spell_details, attack_result):
        super().__init__(session, source, 'searing_smite')
        self.target = target
        self.slot_level = int(slot_level or 1)
        self.spell_details = spell_details
        self.attack_result = attack_result or {}
        self.as_bonus_action = True

    def label(self):
        return f"Searing Smite (Level {self.slot_level})"

    def button_label(self):
        return self.label()

    def name(self):
        return self.label()

    def resolve(self, session, map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        dice = 1 + max(0, self.slot_level - 1)
        attack_roll = self.attack_result.get('attack_roll')
        is_crit = bool(attack_roll is not None and attack_roll.nat_20())
        damage_roll = DieRoll.roll(
            f'{dice}d6',
            crit=is_crit,
            battle=battle,
            entity=self.source,
            description='dice_roll.spells.searing_smite',
        )
        consume_resource(
            battle,
            self.source,
            self.spell_details,
            cast_level=self.slot_level,
            casting_class='paladin',
        )
        if battle is not None:
            state = battle.entity_state_for(self.source)
            if state is not None and state.get('bonus_action', 0) > 0:
                state['bonus_action'] -= 1

        effect = SearingSmiteSpell(
            session, self.source, 'searing_smite', self.spell_details
        )
        effect.ignited_target = self.target
        effect.damage_dice = dice

        self.result = [
            {
                'type': 'spell_damage',
                'source': self.source,
                'target': self.target,
                'attack_name': self.spell_details.get('name', 'Searing Smite'),
                'damage_type': 'fire',
                'damage_roll': damage_roll,
                'damage': damage_roll,
                'attack_roll': attack_roll,
                'spell': self.spell_details,
                'cast_level': self.slot_level,
                'trigger': 'searing_smite',
            },
            {
                'type': 'searing_smite',
                'source': self.source,
                'target': self.target,
                'effect': effect,
                'spell': self.spell_details,
            },
        ]
        return self


class SearingSmiteEffect:
    """Offer Searing Smite as a bonus-action reaction after a melee hit (2024)."""

    def __init__(self, owner):
        self.owner = owner

    def __str__(self):
        return 'searing_smite'

    def on_attack_hit(self, entity, opts=None):
        opts = opts or {}
        if entity != self.owner:
            return []

        session = getattr(entity, 'session', None)
        ruleset = getattr(session, 'ruleset', None) if session else None
        if not (ruleset and ruleset.name == '5e-2024'):
            return []

        prepared = []
        if hasattr(entity, 'prepared_spells'):
            prepared = entity.prepared_spells() or []
        if 'searing_smite' not in prepared:
            return []

        hit_result = opts.get('result') or {}
        if not hit_result.get('hit?'):
            return []
        battle = hit_result.get('battle')
        if battle is None:
            return []
        target = hit_result.get('target')
        if target is None:
            return []
        if hit_result.get('thrown'):
            return []
        if entity.total_bonus_actions(battle) <= 0:
            return []

        weapon_key = hit_result.get('weapon')
        weapon_meta = hit_result.get('npc_action')
        if not weapon_meta and weapon_key:
            weapon_meta = entity.session.load_weapon(weapon_key)
        if not weapon_meta or weapon_meta.get('type') != 'melee_attack':
            return []

        slots = getattr(entity, 'spell_slots', {}).get('paladin', {})
        available = [lvl for lvl, qty in sorted(slots.items()) if lvl > 0 and qty > 0]
        if not available:
            return []

        spell_details = entity.session.load_spell('searing_smite')
        if not spell_details:
            return []
        valid_actions = [
            SearingSmiteAction(entity.session, entity, target, lvl, spell_details, hit_result)
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
                    'type': 'searing_smite',
                    'trigger': 'on_attack_hit',
                    'source': entity,
                    'target': target,
                },
            )

        if hasattr(selected, 'send'):
            raise AsyncReactionHandler(entity, selected, attack_action, 'on_attack_hit')
        if not selected:
            return []
        if isinstance(selected, int) and 0 <= selected < len(valid_actions):
            selected = valid_actions[selected]
        if not isinstance(selected, SearingSmiteAction):
            return []
        resolved = selected.resolve(entity.session, battle.map_for(entity), {'battle': battle})
        return resolved.result if resolved.result else []


class SearingSmiteSpell(Spell):
    """Ongoing ignition: start-of-turn fire + CON save to end. Not concentration (SRD 5.2)."""

    DURATION_SECONDS = 60

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.ignited_target = None
        self.damage_dice = 1
        self._instance_id = f"searing_smite:{id(self)}"

    @property
    def id(self):
        return self._instance_id

    def build_map(self, orig_action):
        # Cast via post-hit BA offer under 2024; direct cast map is a no-op.
        return orig_action

    def resolve(self, entity, battle, spell_action, battle_map):
        return []

    def start_of_turn(self, entity, opt=None):
        if entity is not self.ignited_target:
            return
        battle = (opt or {}).get('battle')
        session = getattr(self, 'session', None) or getattr(self.source, 'session', None)
        dice = max(1, int(self.damage_dice or 1))
        damage_roll = DieRoll.roll(
            f'{dice}d6',
            battle=battle,
            entity=self.source,
            description='dice_roll.spells.searing_smite_ongoing',
        )
        damage_event({
            'source': self.source,
            'target': entity,
            'attack_name': self.properties.get('name', 'Searing Smite'),
            'damage_type': 'fire',
            'damage_roll': damage_roll,
            'damage': damage_roll,
            'spell': self.properties,
        }, battle)

        ability = HoldPersonSpell._caster_spell_ability(self.source, None)
        ability_full = {
            'str': 'strength', 'dex': 'dexterity', 'con': 'constitution',
            'int': 'intelligence', 'wis': 'wisdom', 'cha': 'charisma',
            'strength': 'strength', 'dexterity': 'dexterity',
            'constitution': 'constitution', 'intelligence': 'intelligence',
            'wisdom': 'wisdom', 'charisma': 'charisma',
        }.get(str(ability).lower() if ability else '', 'charisma')
        dc = self.source.spell_save_dc(ability_full)
        save = entity.save_throw('constitution', battle=battle, opts={'is_magical': True})
        if save.result() >= dc:
            # remove_effect on the ignited creature clears start_of_turn hooks
            # and the caster's casted_effects entry.
            entity.remove_effect(self)
            if session:
                session.event_manager.received_event({
                    'event': 'save_success',
                    'source': entity,
                    'save_type': 'constitution',
                    'roll': save,
                    'dc': dc,
                })

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'searing_smite':
            return

        if battle and session is None:
            session = battle.session
        source = item['source']
        target = item['target']
        effect = item['effect']
        effect.ignited_target = target

        # Drop prior searing smite ignition from this caster.
        if source.has_effect('searing_smite'):
            for desc in list(source.effects.get('searing_smite', [])):
                source.dismiss_effect(desc['effect'])

        if session is not None:
            source.add_casted_effect({
                'target': target,
                'effect': effect,
                'expiration': session.game_time + SearingSmiteSpell.DURATION_SECONDS,
            })

        target.register_event_hook(
            'start_of_turn', effect, method_name='start_of_turn', effect=effect, source=source,
            duration=SearingSmiteSpell.DURATION_SECONDS,
        )
        source.register_effect(
            'searing_smite', SearingSmiteSpell,
            effect=effect, source=source,
            duration=SearingSmiteSpell.DURATION_SECONDS,
        )
        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_debuff',
                'spell': effect,
                'source': source,
                'target': target,
            })

    def dismiss(self, entity, _descriptor=None, opts=None):
        # Event hooks are cleared by Entity.remove_effect.
        return
