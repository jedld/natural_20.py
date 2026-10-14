"""Faerie Fire — 1st-level evocation (SRD), concentration up to 1 minute.

Every creature in a 20-foot cube within 60 feet makes a Dexterity save. Those
that fail are outlined in light for the duration:

* ``targeted_advantage_override`` — attack rolls against them have advantage
  when the attacker can see them (read by
  ``natural20.weapons.compute_advantages_and_disadvantages``, which also covers
  spell attacks).
* ``invisibility_suppressed`` — they can't benefit from being invisible
  (``Entity.invisible``).
* ``light_override`` — they shed dim light in a 10-foot radius.

One ``FaerieFireEffect`` holds the caster's concentration and the list of
outlined creatures (stored as entity UIDs so it saves through the generic
``!effect_object`` representer).
"""
from __future__ import annotations

import uuid

from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell

TARGET_EFFECTS = ('targeted_advantage_override', 'invisibility_suppressed', 'light_override')


def _attacker_sees(attacker, target) -> bool:
    if attacker is None:
        return True
    if hasattr(attacker, 'blinded') and attacker.blinded():
        return False
    session = getattr(target, 'session', None)
    battle_map = None
    if session is not None and hasattr(session, 'map_for_entity'):
        try:
            battle_map = session.map_for_entity(target)
        except Exception:
            battle_map = None
    if battle_map is None or attacker not in getattr(battle_map, 'entities', {}):
        return True
    try:
        return bool(battle_map.can_see(attacker, target))
    except Exception:
        return True


class FaerieFireEffect:
    """Concentration marker; outlines every creature in ``target_uids``."""

    DIM_LIGHT_FEET = 10

    def __init__(self, source, target_uids, duration=60, spell_properties=None):
        self.source = source
        self.target_uids = list(target_uids)
        self.duration = int(duration)
        self.spell_properties = dict(spell_properties or {})
        self.uid = f"faerie_fire:{uuid.uuid4().hex[:10]}"
        self.ended = False

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return 'faerie_fire'

    def label(self):
        return self.spell_properties.get('label', 'Faerie Fire')

    def targets(self):
        session = getattr(self.source, 'session', None)
        found = []
        for uid in self.target_uids:
            entity = session.entity_by_uid(uid) if session is not None else None
            if entity is not None:
                found.append(entity)
        return found

    @staticmethod
    def targeted_advantage_override(entity, opt=None):
        attacker = (opt or {}).get('source')
        if _attacker_sees(attacker, entity):
            return [['faerie_fire'], []]
        return [[], []]

    @staticmethod
    def invisibility_suppressed(entity, opt=None):
        return True

    @staticmethod
    def light_override(entity, opt=None):
        opt = opt or {}
        return {
            'bright': opt.get('bright', 0) or 0,
            'dim': max(opt.get('dim', 0) or 0, FaerieFireEffect.DIM_LIGHT_FEET),
        }

    def outline(self, target):
        for effect_type in TARGET_EFFECTS:
            target.register_effect(effect_type, FaerieFireEffect, effect=self,
                                   source=self.source, duration=self.duration)
        if target.entity_uid not in self.target_uids:
            self.target_uids.append(target.entity_uid)

    def dismiss(self, entity, _descriptor=None, opts=None):
        if self.ended:
            return
        self.ended = True
        for target in self.targets():
            target.remove_effect(self)
            _refresh_lights(target)
        source = self.source
        if source is not None and getattr(source, 'concentration', None) is self:
            source.drop_concentration()


def _refresh_lights(target):
    session = getattr(target, 'session', None)
    if session is None or not hasattr(session, 'map_for_entity'):
        return
    try:
        battle_map = session.map_for_entity(target)
    except Exception:
        return
    if battle_map is not None and hasattr(battle_map, 'invalidate_dynamic_lights'):
        battle_map.invalidate_dynamic_lights()


class FaerieFireSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_square',
                'num': 1,
                'range': self.properties.get('range', 60),
                'size': self.properties.get('area_size', 20),
            }],
            'next': set_target,
        }

    def area_squares(self, battle_map, corner):
        x, y = int(corner[0]), int(corner[1])
        side = max(1, int(self.properties.get('area_size', 20)) // battle_map.feet_per_grid)
        return [(x + dx, y + dy) for dx in range(side) for dy in range(side)
                if 0 <= x + dx < battle_map.size[0] and 0 <= y + dy < battle_map.size[1]]

    def creatures_in_area(self, battle_map, corner):
        from natural20.item_library.object import Object
        found = []
        for x, y in self.area_squares(battle_map, corner):
            for entity in battle_map.entities_at(x, y):
                if entity in found or isinstance(entity, Object) or not hasattr(entity, 'register_effect'):
                    continue
                if hasattr(entity, 'dead') and entity.dead():
                    continue
                found.append(entity)
        return found

    def validate(self, battle_map, target=None, battle=None):
        self.clear_validation_errors()
        self.errors = []
        target = target if target is not None else self.target
        if not isinstance(target, (list, tuple)) or len(target) != 2 or hasattr(target[0], 'entity_uid'):
            self.errors.append('Choose a point on the map within range.')
        return len(self.errors) == 0

    def resolve(self, entity, battle, spell_action, battle_map):
        corner = spell_action.target
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        outlined, results = [], []
        for creature in self.creatures_in_area(battle_map, corner):
            save = SaveCheck.make(creature, 'dexterity', dc, battle=battle, opts={'is_magical': True})
            if save.passed:
                results.append({
                    'type': 'spell_miss',
                    'source': entity,
                    'target': creature,
                    'attack_name': 'faerie_fire',
                    'spell_save': save.roll,
                    'dc': dc,
                    'spell': self.properties,
                })
            else:
                outlined.append(creature)
        results.append({
            'type': 'faerie_fire',
            'source': entity,
            'target': list(corner),
            'targets': outlined,
            'squares': [list(s) for s in self.area_squares(battle_map, corner)],
            'dc': dc,
            'effect': self,
            'spell': self.properties,
        })
        return results

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'faerie_fire':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        targets = list(item.get('targets') or [])
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 60))
        session.event_manager.received_event({
            'event': 'faerie_fire',
            'source': source,
            'target': item.get('target'),
            'targets': targets,
        })
        if not targets:
            return None

        effect = FaerieFireEffect(source, [], duration=duration, spell_properties=spell)
        source.add_casted_effect({
            'target': source,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)
        for target in targets:
            effect.outline(target)
            _refresh_lights(target)
        return effect
