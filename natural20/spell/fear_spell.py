"""Fear — 3rd-level illusion (SRD, concentration 1 minute).

A 30-ft cone of nightmare images. Each creature in it makes a Wisdom save or
is Frightened of the caster for the duration (``natural20/utils/fear.py``
``apply_fear`` with ``must_flee``): while frightened it must Dash away from
the caster by the safest route on its turns (AI controllers follow
``flee_source`` / ``flee_choice``; a manually controlled victim must do so
itself). At the end of each of its turns, a frightened creature that can't
see the caster repeats the save, ending the effect on a success.

Simplification: frightened creatures don't drop what they are holding.
"""
from __future__ import annotations

from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell
from natural20.utils.fear import apply_fear, end_fear, is_frightened_of


class FearSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.target_uids = ''
        self.dc = None

    def __str__(self):
        return 'fear'

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_cone',
                'num': 1,
                'range': self.properties.get('range_cone', 30),
                'require_los': True,
            }],
            'next': set_target,
        }

    def _cone_targets(self, entity, battle_map, target):
        if target is None:
            return []
        point = target
        if not isinstance(target, (list, tuple)):
            point = battle_map.position_of(target)
        source_pos = battle_map.position_of(entity)
        squares = battle_map.squares_in_cone(
            source_pos, point,
            int(self.properties.get('range_cone', 30)) // battle_map.feet_per_grid,
            require_los=True)
        out = []
        for square in squares:
            creature = battle_map.entity_at(square[0], square[1])
            if creature is None or creature is entity or creature in out:
                continue
            if getattr(creature, 'object', lambda: False)() or creature.dead():
                continue
            out.append(creature)
        return out

    def compute_hit_probability(self, battle, opts=None):
        entity = self.source
        battle_map = battle.map_for(entity) if battle is not None else None
        if battle_map is None or self.action is None:
            return 0.0
        targets = self._cone_targets(entity, battle_map, self.action.target)
        if not targets:
            return 0.0
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, self.action))
        roll = targets[0].save_throw('wisdom', battle, {'is_magical': True})
        return 1.0 - roll.prob(dc)

    def resolve(self, entity, battle, spell_action, battle_map):
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        self.dc = dc
        results = []
        failed = []
        for creature in self._cone_targets(entity, battle_map, spell_action.target):
            save = SaveCheck.make(creature, 'wisdom', dc, battle,
                                  {'is_magical': True, 'dc': dc, 'condition': 'frightened'},
                                  auto_fail_if_unconscious=False)
            results.append({'target': creature, 'roll': save.roll, 'success': save.passed})
            if not save.passed:
                failed.append(creature)
        return [{
            'type': 'fear',
            'source': entity,
            'target': failed[0] if failed else None,
            'targets': failed,
            'saves': results,
            'dc': dc,
            'effect': self,
            'spell': self.properties,
        }]

    # --- per-target hooks ----------------------------------------------

    def targets(self):
        session = getattr(self.source, 'session', None) or self.session
        out = []
        for uid in [u for u in str(self.target_uids or '').split(',') if u]:
            creature = session.entity_by_uid(uid) if session is not None else None
            if creature is not None:
                out.append(creature)
        return out

    def end_of_turn(self, entity, opts=None):
        """Repeat the save only when the frightened creature can't see the caster."""
        caster = self.source
        if caster is None or not is_frightened_of(entity, caster):
            return None
        battle = (opts or {}).get('battle')
        session = getattr(entity, 'session', None)
        battle_map = battle.map_for(entity) if battle is not None else (
            session.map_for(entity) if session is not None and hasattr(session, 'map_for') else None)
        try:
            sees = battle_map is not None and battle_map.can_see(entity, caster)
        except Exception:
            sees = True
        if sees:
            return None
        dc = int(self.dc or 10)
        roll = entity.save_throw('wisdom', battle, {'is_magical': True, 'dc': dc, 'condition': 'frightened'})
        success = roll.result() >= dc
        entity.session.event_manager.received_event({
            'event': 'fear_save', 'source': caster, 'target': entity,
            'roll': roll, 'dc': dc, 'success': success,
        })
        if success:
            self._release(entity)
        return None

    def _release(self, creature):
        end_fear(creature, self.source.entity_uid)
        hooks = creature.entity_event_hooks.get('end_of_turn') or []
        creature.entity_event_hooks['end_of_turn'] = [h for h in hooks if h.get('effect') is not self]
        uids = [u for u in str(self.target_uids or '').split(',') if u and u != creature.entity_uid]
        self.target_uids = ','.join(uids)
        if not uids and getattr(self.source, 'concentration', None) is self:
            self.source.dismiss_effect(self)

    def _register_target_hook(self, creature, duration=None):
        creature.register_event_hook('end_of_turn', self, 'end_of_turn', effect=self, duration=duration)

    def restore_hooks(self):
        for creature in self.targets():
            if is_frightened_of(creature, self.source):
                self._register_target_hook(creature)

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'fear':
            return None
        source, effect = item['source'], item['effect']
        session = session or (battle.session if battle is not None else source.session)
        duration = int(effect.properties.get('duration_seconds', 60))
        session.event_manager.received_event({
            'event': 'fear', 'source': source,
            'saves': item.get('saves') or [], 'dc': item.get('dc'),
        })
        targets = list(item.get('targets') or [])
        frightened = []
        for creature in targets:
            if apply_fear(creature, source, save_dc=f"wisdom:{item.get('dc')}", duration=duration,
                          label='Fear', must_flee=True):
                frightened.append(creature)
                effect._register_target_hook(creature, duration)
        if not frightened:
            return source
        effect.target_uids = ','.join(c.entity_uid for c in frightened)
        # The cast targeted a cone point; ``Entity.dismiss_effect`` would try to
        # call ``remove_effect`` on it.
        effect.action = None
        source.add_casted_effect({'target': frightened[0], 'effect': effect,
                                  'expiration': session.game_time + duration})
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)
        return source

    def dismiss(self, entity, _descriptor=None, opts=None):
        caster = self.source
        for creature in self.targets():
            if caster is not None:
                end_fear(creature, caster.entity_uid)
            hooks = creature.entity_event_hooks.get('end_of_turn') or []
            creature.entity_event_hooks['end_of_turn'] = [h for h in hooks if h.get('effect') is not self]
        self.target_uids = ''
