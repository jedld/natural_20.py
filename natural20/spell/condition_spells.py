"""YAML-driven "save or suffer a condition" spells.

``ConditionSaveSpell`` reads a ``condition_save`` block from the spell YAML::

    condition_save:
      save: wisdom                    # save ability vs the caster's spell DC
      conditions: [paralyzed]         # statuses added while affected
      charmed: true                   # source-linked charm (can't attack the caster)
      area: {shape: cube, size: 30}   # omit for single-target spells
      creature_types: [beast]         # only these creature types (race list)
      exclude_creature_types: [undead]
      extra_targets_per_slot: 1       # one more target per slot level above the spell's
      targets_within_ft: 30           # extra targets must be this close to each other
      requires_sight: true            # creatures that can't see the caster/area are unaffected
      advantage_in_combat: true       # target saves with advantage while fighting the caster's side
      repeat_save: end_of_turn        # save again at the end of each of its turns
      repeat_save_on_damage: true     # save again whenever it takes damage
      ends_on_damage: true            # damage ends the effect on that creature
      speed_zero: true                # speed 0 while affected
      dominate: true                  # fights for the caster's side while affected
      off_plane: banished             # removed from the plane (natural20/utils/off_plane.py)
      restrict_actions: [attack, spell]   # action_restriction kinds while affected
      ally_condition_immunities: [charmed, frightened]  # allies in the area skip the save and
                                      # gain these immunities instead (Calm Emotions)
      per_turn_damage:                # damage at the start of each of the caster's turns
        dice: 2d8
        damage_type: psychic

One ``ConditionSpellEffect`` holds the caster's concentration and the
affected creatures (stored as UIDs, so it saves through ``!effect_object``).
Entity hooks are not saved; ``restore_hooks`` re-registers them after a load.
"""

from __future__ import annotations

import uuid

from natural20.die_roll import DieRoll
from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell

EFFECT_KEY = 'condition_spell'


def _spec(properties):
    return dict((properties or {}).get('condition_save') or {})


def _creature_types(entity):
    race = (getattr(entity, 'properties', None) or {}).get('race') or []
    if isinstance(race, str):
        race = [race]
    types = {str(r).lower() for r in race}
    if callable(getattr(entity, 'undead', None)) and entity.undead():
        types.add('undead')
    if callable(getattr(entity, 'humanoid', None)) and entity.humanoid():
        types.add('humanoid')
    return types


def eligible(spec, creature):
    """True when ``creature`` can be affected under the spec's type rules."""
    if creature is None or not hasattr(creature, 'register_effect'):
        return False
    if callable(getattr(creature, 'object', None)) and creature.object():
        return False
    types = _creature_types(creature)
    wanted = {str(t).lower() for t in spec.get('creature_types') or []}
    if wanted and not (types & wanted):
        return False
    excluded = {str(t).lower() for t in spec.get('exclude_creature_types') or []}
    if excluded & types:
        return False
    if spec.get('charmed') and creature.immune_to_condition('charmed'):
        return False
    for condition in spec.get('conditions') or []:
        if condition in ('incapacitated',):
            continue
        if creature.immune_to_condition(condition):
            return False
    return True


class ConditionSpellEffect:
    """Concentration marker for one casting; affects every creature in ``target_uids``."""

    def __init__(self, source, spell_properties, dc, duration=60):
        self.source = source
        self.spell_properties = dict(spell_properties or {})
        self.dc = int(dc)
        self.duration = int(duration)
        self.target_uids = []
        self.warded_uids = []
        self.original_groups = {}
        self.uid = f"{self.spell_properties.get('id') or 'condition_spell'}:{uuid.uuid4().hex[:10]}"
        self.ended = False

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return str(self.spell_properties.get('id') or 'condition_spell')

    def label(self):
        return self.spell_properties.get('label') or self.spell_properties.get('name') or str(self)

    @property
    def spec(self):
        return _spec(self.spell_properties)

    def _session(self):
        return getattr(self.source, 'session', None)

    def targets(self):
        session = self._session()
        found = []
        for uid in self.target_uids:
            entity = session.entity_by_uid(uid) if session is not None else None
            if entity is not None:
                found.append(entity)
        return found

    # -- effect handlers -----------------------------------------------------

    @staticmethod
    def speed_override(entity, opt=None):
        return 0

    @staticmethod
    def action_restriction(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        kinds = list(opt.get('value') or [])
        for kind in (effect.spec.get('restrict_actions') if effect is not None else None) or []:
            if kind not in kinds:
                kinds.append(kind)
        return kinds

    @staticmethod
    def condition_immunity(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        found = list(opt.get('value') or [])
        for condition in (effect.spec.get('ally_condition_immunities') if effect is not None else None) or []:
            if condition not in found:
                found.append(condition)
        return found

    def ward(self, target):
        """Ally inside the area: grant ``ally_condition_immunities`` while the spell lasts."""
        target.register_effect('condition_immunity', ConditionSpellEffect, effect=self,
                               source=self.source, duration=self.duration)
        if target.entity_uid not in self.warded_uids:
            self.warded_uids.append(target.entity_uid)

    # -- affliction ------------------------------------------------------------

    def afflict(self, target, battle=None):
        spec = self.spec
        if battle is not None:
            self._battle = battle
        for status in spec.get('conditions') or []:
            if status not in target.statuses:
                target.statuses.append(status)
        if spec.get('charmed'):
            from natural20.utils.monster_traits import apply_charm
            apply_charm(target, self.source, duration=self.duration, repeat_save_when_harmed=False)
        target.register_effect(EFFECT_KEY, ConditionSpellEffect, effect=self,
                               source=self.source, duration=self.duration)
        if spec.get('speed_zero'):
            target.register_effect('speed_override', ConditionSpellEffect, effect=self,
                                   source=self.source, duration=self.duration)
        if spec.get('restrict_actions'):
            target.register_effect('action_restriction', ConditionSpellEffect, effect=self,
                                   source=self.source, duration=self.duration)
        if target.entity_uid not in self.target_uids:
            self.target_uids.append(target.entity_uid)
        if spec.get('dominate'):
            self._switch_side(target, battle)
        if spec.get('off_plane'):
            from natural20.utils.off_plane import send_off_plane
            send_off_plane(target, spec['off_plane'], source=self.source, incapacitated=True)
        self._register_hooks(target)

    def _register_hooks(self, target):
        spec = self.spec
        if spec.get('repeat_save') == 'end_of_turn':
            target.register_event_hook('end_of_turn', self, method_name='on_end_of_turn',
                                       effect=self, source=self.source, duration=self.duration)
        if spec.get('repeat_save_on_damage') or spec.get('ends_on_damage'):
            target.register_event_hook('damage', self, method_name='on_damage',
                                       effect=self, source=self.source, duration=self.duration)
        if spec.get('per_turn_damage') and not getattr(self, '_source_hooked', False):
            self.source.register_event_hook('start_of_turn', self, method_name='on_caster_turn',
                                            effect=self, source=self.source, duration=self.duration)
            self._source_hooked = True

    def restore_hooks(self):
        self._source_hooked = False
        for target in self.targets():
            self._register_hooks(target)

    def _switch_side(self, target, battle):
        if battle is None or target not in getattr(battle, 'entities', {}) \
                or self.source not in battle.entities:
            return
        state = battle.entities[target]
        self.original_groups[target.entity_uid] = state.get('group')
        state['group'] = battle.entities[self.source].get('group')
        state.pop('_wrapped_controller', None)
        self._battle = battle

    def _restore_side(self, target, battle=None):
        group = self.original_groups.pop(target.entity_uid, None)
        if group is None:
            return
        session = self._session()
        battle = (battle or getattr(self, '_battle', None)
                  or getattr(session, 'current_battle', None) or getattr(session, 'battle', None))
        if battle is None:
            from natural20.utils.combat_comms import battle_for
            battle = battle_for(target)
        if battle is not None and target in getattr(battle, 'entities', {}):
            battle.entities[target]['group'] = group

    # -- hooks -----------------------------------------------------------------

    def on_end_of_turn(self, entity, opt=None):
        battle = (opt or {}).get('battle')
        save = SaveCheck.make(entity, self.spec.get('save', 'wisdom'), self.dc, battle=battle,
                              opts={'is_magical': True, 'condition': self._primary_condition()})
        if save.passed:
            self.release(entity, battle=battle, reason='saved')

    def on_damage(self, entity, opt=None):
        opt = opt or {}
        battle = opt.get('battle')
        if self.spec.get('ends_on_damage'):
            self.release(entity, battle=battle, reason='damaged')
            return
        save = SaveCheck.make(entity, self.spec.get('save', 'wisdom'), self.dc, battle=battle,
                              opts={'is_magical': True, 'condition': self._primary_condition()})
        if save.passed:
            self.release(entity, battle=battle, reason='saved')

    def on_caster_turn(self, entity, opt=None):
        spec = self.spec.get('per_turn_damage') or {}
        battle = (opt or {}).get('battle')
        session = self._session()
        for target in self.targets():
            if target.dead():
                continue
            roll = DieRoll.roll(str(spec.get('dice') or '1d6'), entity=self.source, battle=battle,
                                description=f"dice_roll.spells.{self}")
            damage_type = spec.get('damage_type', 'psychic')
            if session is not None:
                session.event_manager.received_event({
                    'event': 'spell_damage', 'source': self.source, 'target': target,
                    'attack_name': str(self), 'damage_type': damage_type,
                    'value': roll.result(), 'spell': self.spell_properties,
                    'damage_roll': roll, 'attack_roll': None, 'advantage_mod': 0,
                })
            target.take_damage(roll.result(), battle=battle, damage_type=damage_type,
                               session=session, roll_info=roll)

    def _primary_condition(self):
        if self.spec.get('charmed'):
            return 'charmed'
        conditions = self.spec.get('conditions') or []
        return conditions[0] if conditions else None

    # -- teardown --------------------------------------------------------------

    def release(self, target, battle=None, reason='ended'):
        """End the effect on one creature; the spell ends when nobody is left."""
        if target.entity_uid not in self.target_uids:
            return
        self.target_uids.remove(target.entity_uid)
        self._clear(target, battle)
        session = self._session()
        if session is not None:
            session.event_manager.received_event({
                'event': 'condition_spell_end', 'source': self.source, 'target': target,
                'spell': self.spell_properties, 'reason': reason,
            })
        if not self.target_uids and not getattr(self, 'warded_uids', None) and not self.ended:
            self.ended = True
            if getattr(self.source, 'concentration', None) is self:
                self.source.dismiss_effect(self)

    def _clear(self, target, battle=None):
        spec = self.spec
        for status in spec.get('conditions') or []:
            if status in target.statuses:
                target.statuses.remove(status)
        if spec.get('charmed'):
            from natural20.utils.monster_traits import end_charm
            end_charm(target, self.source.entity_uid)
        for key in (EFFECT_KEY, 'speed_override', 'action_restriction', 'condition_immunity'):
            target.effects[key] = [d for d in target.effects.get(key, []) if d.get('effect') is not self]
        for key, hooks in list(target.entity_event_hooks.items()):
            target.entity_event_hooks[key] = [h for h in hooks if h.get('effect') is not self]
        self._restore_side(target, battle)
        if spec.get('off_plane'):
            from natural20.utils.off_plane import return_to_plane
            return_to_plane(target, battle or getattr(self, '_battle', None))

    def dismiss(self, entity, _descriptor=None, opts=None):
        """Called when the caster's concentration ends (``Entity.remove_effect``)."""
        if entity is not self.source:
            if entity.entity_uid in self.target_uids:
                self.target_uids.remove(entity.entity_uid)
                self._clear(entity)
            return
        self.ended = True
        for target in self.targets():
            self._clear(target)
        self.target_uids = []
        session = self._session()
        for uid in list(getattr(self, 'warded_uids', None) or []):
            ally = session.entity_by_uid(uid) if session is not None else None
            if ally is not None:
                ally.effects['condition_immunity'] = [
                    d for d in ally.effects.get('condition_immunity', []) if d.get('effect') is not self]
        self.warded_uids = []
        for key, hooks in list(self.source.entity_event_hooks.items()):
            self.source.entity_event_hooks[key] = [h for h in hooks if h.get('effect') is not self]


class ConditionSaveSpell(Spell):
    """Single target or area; see the module docstring for the YAML block."""

    @property
    def spec(self):
        return _spec(self.properties)

    def _extra_targets(self, orig_action):
        per_slot = int(self.spec.get('extra_targets_per_slot') or 0)
        base = int(self.properties.get('level', 1) or 1)
        at_level = int(getattr(orig_action, 'at_level', None) or base)
        return max(0, at_level - base) * per_slot

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        area = self.spec.get('area')
        if area:
            shape = str(area.get('shape') or 'radius')
            param = {'type': 'select_radius' if shape in ('radius', 'sphere') else 'select_square',
                     'num': 1, 'range': self.properties.get('range', 60)}
            if shape in ('radius', 'sphere'):
                param['radius'] = int(area.get('size', 20))
            else:
                param['size'] = int(area.get('size', 20))
            return {'param': [param], 'next': set_target}

        param = {
            'type': 'select_target',
            'num': 1 + self._extra_targets(orig_action),
            'min': 1,
            'range': self.properties.get('range', 60),
            'unique_targets': True,
            'target_types': self.properties.get('target_types') or ['enemies'],
        }
        types = self.spec.get('creature_types') or []
        if types == ['humanoid']:
            param['require_humanoid'] = True
        elif types:
            param['require_races'] = [str(t) for t in types]
        excluded_types = self.spec.get('exclude_creature_types') or []
        if excluded_types:
            param['exclude_races'] = [str(t) for t in excluded_types]
        return {'param': [param], 'next': set_target}

    # -- targeting -------------------------------------------------------------

    def _area_squares(self, battle_map, point):
        area = self.spec.get('area') or {}
        size = int(area.get('size', 20))
        x, y = int(point[0]), int(point[1])
        if str(area.get('shape') or 'radius') in ('radius', 'sphere'):
            return battle_map.squares_in_radius((x, y), size)
        side = max(1, size // battle_map.feet_per_grid)
        return [(x + dx, y + dy) for dx in range(side) for dy in range(side)
                if 0 <= x + dx < battle_map.size[0] and 0 <= y + dy < battle_map.size[1]]

    def _targets(self, entity, battle_map, spell_action):
        target = spell_action.target
        if self.spec.get('area'):
            if not isinstance(target, (list, tuple)) or len(target) != 2 or hasattr(target[0], 'entity_uid'):
                return []
            found = []
            for x, y in self._area_squares(battle_map, target):
                for creature in battle_map.entities_at(x, y):
                    if creature not in found and creature is not entity and hasattr(creature, 'register_effect'):
                        found.append(creature)
            return found
        if isinstance(target, tuple):
            target = list(target)
        if not isinstance(target, list):
            target = [target] if target is not None else []
        return [t for t in target if hasattr(t, 'register_effect')]

    def _within(self, battle_map, targets):
        max_ft = self.spec.get('targets_within_ft')
        if not max_ft or battle_map is None or len(targets) <= 1:
            return True
        for i, first in enumerate(targets):
            for second in targets[i + 1:]:
                if battle_map.distance(first, second) * battle_map.feet_per_grid > int(max_ft):
                    return False
        return True

    def _can_see_caster(self, creature, entity, battle_map):
        if not self.spec.get('requires_sight') or battle_map is None:
            return True
        if callable(getattr(creature, 'blinded', None)) and creature.blinded():
            return False
        try:
            return bool(battle_map.can_see(creature, entity))
        except Exception:
            return True

    @staticmethod
    def _ally(creature, entity, battle):
        if creature is entity:
            return True
        try:
            if battle is not None and creature in battle.entities and entity in battle.entities:
                return not battle.opposing(creature, entity)
        except Exception:
            pass
        return getattr(creature, 'group', None) == getattr(entity, 'group', None)

    def _fighting(self, creature, entity, battle):
        if battle is None or not self.spec.get('advantage_in_combat'):
            return False
        try:
            return battle.ongoing() and creature in battle.entities and battle.opposing(creature, entity)
        except Exception:
            return False

    # -- resolution ------------------------------------------------------------

    def resolve(self, entity, battle, spell_action, battle_map):
        spec = self.spec
        name = self.properties.get('id') or str(self)
        targets = self._targets(entity, battle_map, spell_action)
        if not targets:
            return [{'type': 'spell_miss', 'source': entity, 'target': entity, 'attack_name': name,
                     'message': 'no_target', 'spell': self.properties}]
        if not self._within(battle_map, targets):
            return [{'type': 'spell_miss', 'source': entity, 'target': entity, 'attack_name': name,
                     'message': 'targets_too_far_apart', 'spell': self.properties}]

        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        results, afflicted, warded = [], [], []
        for creature in targets:
            if spec.get('ally_condition_immunities') and not creature.dead() and eligible(spec, creature) \
                    and self._ally(creature, entity, battle):
                warded.append(creature)
                continue
            if creature.dead() or not eligible(spec, creature) or not self._can_see_caster(creature, entity, battle_map):
                results.append({'type': 'spell_miss', 'source': entity, 'target': creature,
                                'attack_name': name, 'message': 'unaffected', 'spell': self.properties})
                continue
            opts = {'is_magical': True, 'condition': spec.get('charmed') and 'charmed'
                    or (spec.get('conditions') or [None])[0]}
            if self._fighting(creature, entity, battle):
                opts['advantage'] = ['fighting_caster']
            save = SaveCheck.make(creature, spec.get('save', 'wisdom'), dc, battle=battle, opts=opts)
            if save.passed:
                results.append({'type': 'spell_resist', 'source': entity, 'target': creature,
                                'attack_name': name, 'save_roll': save.roll, 'save_dc': dc,
                                'spell': self.properties})
            else:
                afflicted.append(creature)
        results.append({
            'type': 'condition_spell', 'source': entity, 'targets': afflicted, 'warded': warded,
            'target': afflicted[0] if afflicted else spell_action.target,
            'dc': dc, 'spell': self.properties, 'effect': self,
        })
        return results

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'condition_spell':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        targets = list(item.get('targets') or [])
        warded = list(item.get('warded') or [])
        spell = item.get('spell') or {}
        if not targets and not warded:
            return None
        duration = int(spell.get('duration_seconds', 60))
        effect = ConditionSpellEffect(source, spell, item.get('dc', 10), duration=duration)
        source.add_casted_effect({'target': source, 'effect': effect,
                                  'expiration': session.game_time + duration})
        if spell.get('concentration'):
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)
        for ally in warded:
            effect.ward(ally)
            session.event_manager.received_event({
                'event': 'spell_buf', 'spell': spell, 'source': source, 'target': ally,
            })
        for target in targets:
            effect.afflict(target, battle)
            session.event_manager.received_event({
                'event': 'spell_debuff', 'spell': item.get('effect'),
                'source': source, 'target': target,
            })
        return effect
