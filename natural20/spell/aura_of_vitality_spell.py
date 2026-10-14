"""Aura of Vitality — 3rd-level evocation (SRD), concentration up to 1 minute.

Healing energy radiates from the caster in a 30-foot emanation that moves with
them. Until the spell ends, the caster can use a Bonus Action on their turn to
have one creature in the aura (including themselves) regain 2d6 hit points —
``AuraOfVitalityHealAction``, offered while concentrating on the aura, at most
once per turn.

Edition differences:

* 5e-2024 casts the spell as a Bonus Action and the casting itself heals one
  creature in the aura (a target is picked when casting). That counts as this
  turn's pulse.
* 2014 casts it as an Action with no immediate healing; the Bonus Action pulse
  is available on the same turn.

Every heal is a ``spell_heal`` item, so Beacon of Hope maximization, Disciple
of Life and the combat log apply.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


class AuraOfVitalityEffect:
    """Concentration marker for an active aura."""

    def __init__(self, source, spell_properties=None):
        self.source = source
        self.spell_properties = dict(spell_properties or {})
        self.last_pulse_turn = None

    @property
    def id(self):
        return 'aura_of_vitality'

    def __str__(self):
        return 'aura_of_vitality'

    def label(self):
        return 'Aura of Vitality'

    def radius_ft(self):
        return int(self.spell_properties.get('radius', 30))

    def heal_dice(self):
        return str(self.spell_properties.get('heal_dice', '2d6'))

    def dismiss(self, entity, effect, opts=None):
        return None


def aura_turn_key(battle):
    return [battle.current_round(), getattr(battle, 'current_turn_index', 0)]


def aura_heal_item(source, target, effect, battle, spell_properties=None):
    props = spell_properties or effect.spell_properties
    roll = DieRoll.roll(effect.heal_dice(), battle=battle, entity=source,
                        description='dice_roll.spells.aura_of_vitality')
    return {
        'source': source,
        'target': target,
        'type': 'spell_heal',
        'heal_roll': roll,
        'at_level': props.get('level', 3),
        'spell': props,
    }


def _heals_on_cast(session):
    ruleset = getattr(session, 'ruleset', None)
    return getattr(ruleset, 'name', None) == '5e-2024'


class AuraOfVitalitySpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        if _heals_on_cast(self.session):
            return {
                'param': [{
                    'type': 'select_target',
                    'num': 1,
                    'range': int(self.properties.get('radius', 30)),
                    'auto_pick': 'most_wounded',
                    'target_types': ['allies', 'self'],
                }],
                'next': set_target,
            }
        return {
            'param': [{'type': 'select_emanation', 'range': int(self.properties.get('radius', 30))}],
            'next': lambda _target: set_target(orig_action.source),
        }

    def compute_hit_probability(self, battle, opts=None):
        return 1.0

    def avg_damage(self, battle, opts=None):
        if not _heals_on_cast(self.session):
            return 0
        return -DieRoll.roll(str(self.properties.get('heal_dice', '2d6'))).expected()

    def resolve(self, entity, battle, spell_action, battle_map):
        effect = AuraOfVitalityEffect(entity, self.properties)
        results = [{
            'type': 'aura_of_vitality',
            'source': entity,
            'target': entity,
            'effect': self,
            'aura': effect,
            'spell': self.properties,
        }]
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else None
        if _heals_on_cast(self.session) and target is not None and hasattr(target, 'heal'):
            results.append(aura_heal_item(entity, target, effect, battle, self.properties))
            results[0]['pulsed'] = True
        return results

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'aura_of_vitality':
            return None
        if battle is not None and session is None:
            session = battle.session
        source = item['source']
        aura = item['aura']
        if battle is not None and item.get('pulsed'):
            aura.last_pulse_turn = aura_turn_key(battle)
        duration = int((item.get('spell') or {}).get('duration_seconds', 60))

        source.remove_effect('aura_of_vitality')
        source.add_casted_effect({
            'target': source,
            'effect': aura,
            'expiration': session.game_time + duration,
        })
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, aura)
        else:
            source.concentration_on(aura)

        session.event_manager.received_event({
            'event': 'aura_of_vitality',
            'source': source,
            'target': source,
            'spell': aura,
        })
        return source
