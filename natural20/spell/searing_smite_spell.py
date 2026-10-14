"""Searing Smite — 1st-level paladin evocation (SRD 5.2). BA after melee hit; not concentration."""

from natural20.die_roll import DieRoll
from natural20.spell.extensions.post_hit_smite import PostHitSmiteAction, PostHitSmiteOffer
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell
from natural20.utils.attack_util import damage_event


class SearingSmiteAction(PostHitSmiteAction):
    """Apply Searing Smite after a confirmed melee hit (bonus action, 2024)."""

    SPELL_ID = 'searing_smite'
    DAMAGE_TYPE = 'fire'

    def rider_items(self, battle, damage_roll):
        effect = SearingSmiteSpell(
            self.session, self.source, 'searing_smite', self.spell_details
        )
        effect.ignited_target = self.target
        effect.damage_dice = self.damage_dice_count()
        return [{
            'type': 'searing_smite',
            'source': self.source,
            'target': self.target,
            'effect': effect,
            'spell': self.spell_details,
        }]


class SearingSmiteEffect(PostHitSmiteOffer):
    """Offer Searing Smite as a bonus action after a melee hit.

    Only under the 5e-2024 ruleset: the 2014 Searing Smite is a different
    spell (cast before the attack, concentration)."""

    SPELL_ID = 'searing_smite'
    ACTION_CLASS = SearingSmiteAction
    REQUIRED_RULESET = '5e-2024'


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
        save = entity.save_throw('constitution', battle=battle, opts={'is_magical': True, 'dc': dc})
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
