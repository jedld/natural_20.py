"""Mirror of Reflected Pasts (Explorer's Guide to Wildemount) — gaze item.

Item YAML (``item_class: MirrorWardItem``)::

    mirror_of_reflected_pasts:
      item_class: MirrorWardItem
      usable: true
      activation: action
      requires_attunement: true
      gaze_dc: 15
      gaze_range_ft: 30
      charges: 1        # once per dawn (modelled per long rest)

Speaking the command word (an action) activates the mirror; it hovers in the
air at the activator's position and cannot be moved until deactivated (same
command word, or the effect is dismissed). Each turn at the start of the
activator's turn, every non-Construct creature other than the activator that
is within the gaze range and has line of sight to the mirror makes a Wisdom
saving throw (DC from ``gaze_dc``). On a failure it is paralyzed until the
mirror is deactivated, until it can no longer see the mirror, or until it
succeeds on the repeat save at the end of its turn. A creature that saves, or
whose paralysis ends, is immune for the next 24 hours (stored in
``properties['mirror_gaze_immune_until']``).

"Sees its reflection" is approximated by line of sight to the mirror square.
"""
from __future__ import annotations

from natural20.item_library.object import Object

IMMUNITY_SECONDS = 24 * 3600
SQUARE_FT = 5


class MirrorGazeEffect:

    def __init__(self, source, item_properties=None):
        self.source = source
        self.item_properties = dict(item_properties or {})
        self.target_uids = []

    @property
    def id(self):
        return 'mirror_gaze'

    def __str__(self):
        return self.id

    def label(self):
        return 'Mirror of Reflected Pasts'

    # -- configuration -------------------------------------------------------

    def dc(self):
        return int(self.item_properties.get('gaze_dc') or 15)

    def radius_squares(self):
        return max(1, int(int(self.item_properties.get('gaze_range_ft') or 30)
                          / SQUARE_FT))

    # -- hooks -----------------------------------------------------------------

    def register_hooks(self):
        self.source.register_event_hook('start_of_turn', self,
                                        method_name='on_owner_turn', effect=self)

    def restore_hooks(self):
        self.register_hooks()

    def _immune(self, creature):
        until = getattr(creature, 'properties', {}).get('mirror_gaze_immune_until')
        session = getattr(creature, 'session', None)
        return until is not None and session is not None \
            and session.game_time < int(until)

    def _grant_immunity(self, creature):
        session = getattr(creature, 'session', None)
        if session is not None and isinstance(creature.properties, dict):
            creature.properties['mirror_gaze_immune_until'] = \
                session.game_time + IMMUNITY_SECONDS

    def _visible_targets(self, battle=None):
        if battle is None:
            from natural20.utils.combat_comms import battle_for
            battle = battle_for(self.source)
        if battle is None:
            return []
        battle_map = battle.map_for(self.source) if self.source in battle.entities else None
        if battle_map is None:
            return []
        origin = battle_map.position_of(self.source)
        if origin is None:
            return []
        found = []
        radius = self.radius_squares()
        for entity in list(battle.entities):
            if entity is self.source or entity.dead():
                continue
            if getattr(entity, 'object', lambda: False)():
                continue
            if entity.paralyzed() and entity.entity_uid in self.target_uids:
                continue
            if self._immune(entity):
                continue
            types = set()
            try:
                from natural20.spell.condition_spells import _creature_types
                types = {str(t).lower() for t in (_creature_types(entity) or [])}
            except Exception:
                pass
            if 'construct' in types:
                continue
            pos = battle_map.position_of(entity)
            if pos is None:
                continue
            if max(abs(pos[0] - origin[0]), abs(pos[1] - origin[1])) > radius:
                continue
            if not battle_map.line_of_sight(origin[0], origin[1], pos[0], pos[1]):
                continue
            found.append((entity, battle, battle_map))
        return found

    def on_owner_turn(self, entity, opt=None):
        battle_opt = (opt or {}).get('battle')
        for target, battle, battle_map in self._visible_targets(battle=battle_opt):
            save = target.save_throw('wisdom', battle,
                                     {'is_magical': True, 'dc': self.dc(),
                                      'condition': 'paralyzed'})
            if save is not None and save >= self.dc():
                self._grant_immunity(target)
                continue
            if target.entity_uid not in self.target_uids:
                self.target_uids.append(target.entity_uid)
            if 'paralyzed' not in target.statuses:
                target.statuses.append('paralyzed')
            target.register_event_hook('end_of_turn', self,
                                       method_name='on_target_end_of_turn',
                                       effect=self)
            session = getattr(target, 'session', None)
            if session is not None:
                session.event_manager.received_event({
                    'event': 'mirror_gaze', 'source': self.source, 'target': target,
                })
        return None

    def on_target_end_of_turn(self, entity, opt=None):
        battle = (opt or {}).get('battle')
        save = entity.save_throw('wisdom', battle,
                                 {'is_magical': True, 'dc': self.dc(),
                                  'condition': 'paralyzed'})
        if save is not None and save >= self.dc():
            self._release(entity, battle)

    def _release(self, target, battle=None):
        if target.entity_uid in self.target_uids:
            self.target_uids.remove(target.entity_uid)
        if 'paralyzed' in (target.statuses or []):
            target.statuses.remove('paralyzed')
        for key, hooks in list(target.entity_event_hooks.items()):
            target.entity_event_hooks[key] = [h for h in hooks
                                              if h.get('effect') is not self]
        self._grant_immunity(target)

    def dismiss(self, entity, descriptor=None, opts=None):
        from natural20.utils.combat_comms import battle_for
        battle = battle_for(self.source)
        session = getattr(self.source, 'session', None)
        for uid in list(self.target_uids):
            target = session.entity_by_uid(uid) if session is not None else None
            if target is not None:
                self._release(target, battle)
        self.target_uids = []


class MirrorWardItem(Object):

    def consumable(self):
        return False

    def _resource_name(self):
        return f"{self.properties.get('name') or 'mirror_of_reflected_pasts'}_uses"

    def can_use(self, entity, battle):
        return True

    def build_map(self, action):
        def set_target(target):
            action.target = target
            return action

        return {'param': [{'type': 'select_target', 'num': 1, 'range': 0,
                           'target_types': ['self']}],
                'next': set_target}

    def resolve(self, entity, battle, action, _battle_map):
        return {}

    def use(self, entity, result, session=None):
        user = (result or {}).get('source') or entity
        if user is None:
            return
        session = getattr(user, 'session', None) or session
        active = user.has_effect('mirror_gaze')
        if active:
            # Deactivate: end the gaze (and grant the usual 24h immunity).
            user.remove_effect('mirror_gaze')
            statuses = getattr(user, 'statuses', None)
            if isinstance(statuses, list) and 'mirror_gaze' in statuses:
                statuses.remove('mirror_gaze')
            if session is not None:
                session.event_manager.received_event({
                    'event': 'mirror_gaze_end', 'source': user, 'target': user})
            return
        # Activate: once per dawn.
        name = self._resource_name()
        uses = int(self.properties.get('charges') or 1)
        resource = user.get_resource(name) if hasattr(user, 'get_resource') else None
        if resource is None:
            resource = user.register_resource(name, uses, restore_on='long_rest')
        if resource.current <= 0:
            return
        resource.consume(1)
        effect = MirrorGazeEffect(user, self.properties)
        user.register_effect('mirror_gaze', MirrorGazeEffect, effect=effect,
                             source=user)
        user.add_casted_effect({'target': user, 'effect': effect,
                                'expiration': (getattr(user, 'session', None).game_time
                                               if getattr(user, 'session', None) else 0)
                                + 24 * 3600})
        effect.register_hooks()
        statuses = getattr(user, 'statuses', None)
        if isinstance(statuses, list) and 'mirror_gaze' not in statuses:
            statuses.append('mirror_gaze')
        if session is not None:
            session.event_manager.received_event({
                'event': 'mirror_gaze_start', 'source': user, 'target': user})
