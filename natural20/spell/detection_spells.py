"""Divination spells that sense creatures or contact other planes.

``SenseCreaturesSpell`` (Detect Evil and Good, Detect Poison and Disease)
reads a ``detect`` block::

    detect:
      creature_types: [aberration, celestial, elemental, fey, fiend, undead]
      poisonous: true          # creatures with poison attacks or a `poisonous` property
      statuses: [poisoned, diseased]   # creatures carrying these conditions

On casting, and at the start of each of the caster's turns while
concentration lasts, it emits a ``detect_creatures`` event listing matching
creatures within ``range`` feet (walls block it, as total cover). Consecrated
places and objects are narrative only.

``ContactOtherPlaneSpell`` (1 minute, so out of combat only): Intelligence save
vs ``contact.dc`` (15). On a failure the caster takes ``contact.damage``
(6d6 psychic) and gains ``contact.statuses`` until a long rest; on a success
the caster can ask questions (``contact_other_plane`` event for the DM). A free
cast whose ``free_casts`` entry sets ``auto_succeed_save: true`` (warlock
Contact Patron) skips the save.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


def _creature_types(entity):
    from natural20.spell.condition_spells import _creature_types as types
    return types(entity)


def _poisonous(entity):
    props = getattr(entity, 'properties', None) or {}
    if props.get('poisonous') or props.get('venomous'):
        return True
    for action in props.get('actions') or []:
        if not isinstance(action, dict):
            continue
        if action.get('damage_type') == 'poison':
            return True
        if 'poison' in str(action.get('additional_damage_type') or ''):
            return True
        for extra in action.get('additional_damage') or []:
            if isinstance(extra, dict) and extra.get('damage_type') == 'poison':
                return True
    return False


def matches(detect, creature):
    types = {str(t).lower() for t in detect.get('creature_types') or []}
    if types and types & _creature_types(creature):
        return True
    if detect.get('poisonous') and _poisonous(creature):
        return True
    statuses = set(detect.get('statuses') or [])
    if statuses and statuses & set(getattr(creature, 'statuses', None) or []):
        return True
    return False


def sense_creatures(caster, detect, range_ft, battle=None):
    session = caster.session
    battle_map = battle.map_for(caster) if battle is not None else session.map_for_entity(caster)
    if battle_map is None:
        return []
    found = []
    for creature in list(battle_map.entities.keys()):
        if creature is caster or not hasattr(creature, 'statuses'):
            continue
        if callable(getattr(creature, 'dead', None)) and creature.dead():
            continue
        try:
            distance = battle_map.distance(caster, creature) * battle_map.feet_per_grid
        except Exception:
            continue
        if distance > range_ft:
            continue
        try:
            (cx, cy), (tx, ty) = battle_map.position_of(caster), battle_map.position_of(creature)
            if not battle_map.line_of_sight(cx, cy, tx, ty):
                continue
        except Exception:
            pass
        if matches(detect, creature):
            pos = battle_map.position_of(creature)
            found.append({'entity': creature, 'name': creature.label() if hasattr(creature, 'label') else creature.name,
                          'types': sorted(_creature_types(creature)), 'position': list(pos) if pos else None})
    return found


class SenseCreaturesEffect:
    def __init__(self, source, spell_properties, duration):
        self.source = source
        self.spell_properties = dict(spell_properties or {})
        self.duration = int(duration)
        self.ended = False

    @property
    def id(self):
        return str(self.spell_properties.get('id') or 'sense_creatures')

    def __str__(self):
        return self.id

    def scan(self, battle=None):
        found = sense_creatures(self.source, self.spell_properties.get('detect') or {},
                                int(self.spell_properties.get('range', 30)), battle)
        self.source.session.event_manager.received_event({
            'event': 'detect_creatures', 'source': self.source, 'target': self.source,
            'spell': self.spell_properties, 'found': found,
        })
        return found

    def register_hooks(self):
        self.source.register_event_hook('start_of_turn', self, method_name='on_start_of_turn',
                                        effect=self, source=self.source, duration=self.duration)

    def restore_hooks(self):
        if not self.ended:
            self.register_hooks()

    def on_start_of_turn(self, entity, opt=None):
        if not self.ended:
            self.scan((opt or {}).get('battle'))

    def dismiss(self, entity, _descriptor=None, opts=None):
        self.ended = True
        for key, hooks in list(entity.entity_event_hooks.items()):
            entity.entity_event_hooks[key] = [h for h in hooks if h.get('effect') is not self]
        status = self.id
        if status in entity.statuses:
            entity.statuses.remove(status)


class SenseCreaturesSpell(Spell):
    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = self.source
        return action

    def resolve(self, entity, battle, spell_action, battle_map):
        return [{'type': 'sense_creatures', 'source': entity, 'target': entity,
                 'spell': self.properties, 'effect': self}]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'sense_creatures':
            return None
        source = item['source']
        session = session or (battle.session if battle is not None else source.session)
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 600))
        effect = SenseCreaturesEffect(source, spell, duration)
        source.remove_effect(effect.id)
        source.add_casted_effect({'target': source, 'effect': effect,
                                  'expiration': session.game_time + duration})
        if effect.id not in source.statuses:
            source.statuses.append(effect.id)
        if spell.get('concentration'):
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)
        effect.register_hooks()
        effect.scan(battle)
        return effect


def _free_cast_flag(caster, spell_action, flag, slug=None):
    pool = getattr(spell_action, 'free_cast_pool', None) or getattr(getattr(spell_action, 'action', None),
                                                                     'free_cast_pool', None)
    if not pool:
        return False
    from natural20.utils.class_mechanics import AT_WILL_POOL, free_cast_specs, stored_spell
    for _klass, spec in free_cast_specs(caster):
        spec_pool = AT_WILL_POOL if spec.get('at_will') else spec.get('pool')
        if spec_pool == pool and spec.get(flag):
            if slug is None or stored_spell(caster, spec) in (None, slug):
                return True
    return False


class ContactOtherPlaneSpell(Spell):
    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = self.source
        return action

    def resolve(self, entity, battle, spell_action, battle_map):
        contact = self.properties.get('contact') or {}
        dc = int(contact.get('dc', 15))
        if _free_cast_flag(entity, spell_action, 'auto_succeed_save', self.properties.get('id')):
            return [{'type': 'contact_other_plane', 'source': entity, 'target': entity, 'success': True,
                     'auto': True, 'dc': dc, 'spell': self.properties, 'effect': self}]
        from natural20.spell.extensions.save_check import SaveCheck
        save = SaveCheck.make(entity, contact.get('save', 'intelligence'), dc, battle=battle,
                              opts={'is_magical': True})
        item = {'type': 'contact_other_plane', 'source': entity, 'target': entity, 'success': save.passed,
                'save_roll': save.roll, 'dc': dc, 'spell': self.properties, 'effect': self}
        if not save.passed:
            item['damage_roll'] = DieRoll.roll(str(contact.get('damage', '6d6')), entity=entity, battle=battle,
                                               description='dice_roll.spells.contact_other_plane')
        return [item]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'contact_other_plane':
            return None
        source = item['source']
        session = session or (battle.session if battle is not None else source.session)
        contact = (item.get('spell') or {}).get('contact') or {}
        session.event_manager.received_event({
            'event': 'contact_other_plane', 'source': source, 'target': source,
            'success': bool(item.get('success')), 'auto': bool(item.get('auto')),
            'roll': item.get('save_roll'), 'dc': item.get('dc'),
            'questions': int(contact.get('questions', 5)),
        })
        roll = item.get('damage_roll')
        if roll is not None:
            source.take_damage(roll.result(), battle=battle, damage_type=contact.get('damage_type', 'psychic'),
                               session=session, roll_info=roll)
            for status in contact.get('statuses') or ['incapacitated', 'insanity']:
                if not source.dead() and status not in source.statuses:
                    source.statuses.append(status)
        return source
