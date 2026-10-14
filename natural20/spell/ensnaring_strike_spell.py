"""Ensnaring Strike — 1st-level ranger conjuration (SRD 5.2; 2014 PHB timing via YAML).

Delivered by a weapon hit (``natural20/spell/extensions/weapon_hit_spell.py``):

* 2024 (``weapon_hit.timing: after_hit``): Bonus Action right after hitting.
* 2014 (``timing: next_hit``): cast as a Bonus Action, fires on the next hit.

The creature hit makes a Strength save (advantage if Large or larger). On a
failure it is Restrained by thorny vines until the spell ends (concentration,
1 minute) and takes 1d6 piercing damage (+1d6 per slot level above 1st) at the
start of each of its turns. It (or a creature within reach) can take an action
for a Strength (Athletics) check against the spell save DC to tear free
(``BreakFreeAction`` via the ``escapable_restraint`` effect).
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.extensions.weapon_hit_spell import WeaponHitSpell
from natural20.utils.attack_util import damage_event

LARGE_SIZES = ('large', 'huge', 'gargantuan')


class EnsnaringStrikeSpell(WeaponHitSpell):
    SLUG = 'ensnaring_strike'
    DURATION_SECONDS = 60
    escape_skill = 'athletics'
    escape_label = 'Ensnaring Strike'

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.escape_dc = None
        self.damage_dice = 1

    def keeps_concentration_after_trigger(self):
        return True

    def dice_for(self, slot_level):
        base = int(self.properties.get('level') or 1)
        return 1 + max(0, int(slot_level or base) - base)

    def on_weapon_hit(self, caster, target, hit_result, slot_level, battle):
        dc = self.save_dc(caster)
        size = str(target.size_identifier() if hasattr(target, 'size_identifier') else '').lower()
        opts = {'is_magical': True, 'dc': dc, 'condition': 'restrained'}
        if size in LARGE_SIZES:
            opts['advantage'] = ['large_creature']
        save = SaveCheck.make(target, 'strength', dc, battle, opts)
        item = {
            'type': 'ensnaring_strike',
            'source': caster,
            'target': target,
            'effect': self,
            'spell': self.properties,
            'dc': dc,
            'roll': save.roll,
            'success': save.passed,
            'dice': self.dice_for(slot_level),
        }
        return [item]

    # --- target-side effect handlers ----------------------------------

    @staticmethod
    def restrained_override(entity, opt=None):
        return True

    def start_of_turn(self, entity, opt=None):
        if entity is not self.target or entity.dead():
            return
        battle = (opt or {}).get('battle')
        roll = DieRoll.roll(f"{max(1, int(self.damage_dice or 1))}d6", battle=battle, entity=self.source,
                            description='dice_roll.spells.ensnaring_strike')
        damage_event({
            'source': self.source,
            'target': entity,
            'attack_name': self.properties.get('name', 'Ensnaring Strike'),
            'damage_type': 'piercing',
            'damage_roll': roll,
            'damage': roll,
            'spell': self.properties,
        }, battle)

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'ensnaring_strike':
            return WeaponHitSpell.apply(battle, item, session)
        source, target, effect = item['source'], item['target'], item['effect']
        session = session or (battle.session if battle is not None else source.session)
        if item.get('success'):
            session.event_manager.received_event({
                'event': 'ensnaring_strike', 'source': source, 'target': target,
                'success': True, 'roll': item.get('roll'), 'dc': item.get('dc'),
            })
            if getattr(source, 'concentration', None) is effect:
                source.dismiss_effect(effect)
            return target
        effect.target = target
        effect.escape_dc = int(item['dc'])
        effect.damage_dice = int(item.get('dice') or 1)
        duration = int(effect.properties.get('duration_seconds', EnsnaringStrikeSpell.DURATION_SECONDS))
        if getattr(source, 'concentration', None) is not effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)
        source.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + duration})
        for key in ('restrained_override', 'escapable_restraint', 'ensnaring_strike'):
            target.register_effect(key, EnsnaringStrikeSpell, effect=effect, source=source, duration=duration)
        effect._register_target_hooks(duration)
        session.event_manager.received_event({
            'event': 'ensnaring_strike', 'source': source, 'target': target,
            'success': False, 'roll': item.get('roll'), 'dc': item.get('dc'),
        })
        return target

    @staticmethod
    def escapable_restraint(entity, opt=None):
        return True

    @staticmethod
    def ensnaring_strike(entity, opt=None):
        return True

    def _register_target_hooks(self, duration=None):
        if self.target is None or not hasattr(self.target, 'register_event_hook'):
            return
        self.target.register_event_hook('start_of_turn', self, 'start_of_turn', effect=self,
                                        source=self.source, duration=duration)

    def restore_hooks(self):
        super().restore_hooks()
        if self.escape_dc and self.target is not None and self.target is not self.source:
            self._register_target_hooks()

    def break_free(self, creature, by=None):
        source = self.source
        if source is not None and getattr(source, 'concentration', None) is self:
            source.dismiss_effect(self)
        else:
            creature.remove_effect(self)

    def dismiss(self, entity, _descriptor=None, opts=None):
        super().dismiss(entity, _descriptor, opts)
        target = self.target
        if target is not None and target is not entity and hasattr(target, 'remove_effect'):
            self.target = None
            target.remove_effect(self)
        source = self.source
        if source is not None and getattr(source, 'concentration', None) is self:
            source.drop_concentration()
