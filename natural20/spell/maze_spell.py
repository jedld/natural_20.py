"""Maze — 8th-level conjuration (SRD, concentration, up to 10 minutes).

Full pocket-dimension model (``natural20.utils.pocket_dimension``): the target
is banished from the map into a procedurally generated labyrinth map with a
hostile minotaur roaming it (spawned at the cell farthest from the entrance).
The two simply live on different maps — nothing from outside can reach the
target, and the target cannot walk back out (the doorway is not climbable).

On its turn the trapped creature can spend an action on the spell's
Intelligence check (``escape_dc``, DC 20); minotaurs and goristras
(``auto_escape``) succeed automatically. A success — or the spell ending for
any other reason (concentration broken, expiry, Dispel Magic on the entrance
square) — collapses the demiplane: the creature reappears in the square it
vanished from (or the nearest unoccupied one) and the minotaur vanishes with
the space.
"""
from __future__ import annotations

from natural20.spell.spell import Spell


class MazeSpell(Spell):
    """Spell object + effect handler for one banishment."""

    TARGET_TYPES = ['enemies']

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.zone_id = ''
        self.pocket_map_name = ''
        self.target_uid = ''
        self.warden_uid = ''

    def __str__(self):
        return 'maze'

    # --- targeting -----------------------------------------------------------

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target[0] if isinstance(target, (list, tuple)) else target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 60),
                'unique_targets': True,
                'target_types': self.TARGET_TYPES,
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else None
        if target is None or target is entity or target.dead():
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': entity,
                'attack_name': 'maze',
                'message': 'no_target',
                'spell': self.properties,
            }]
        return [{
            'type': 'maze',
            'source': entity,
            'target': target,
            'attack_name': 'maze',
            'spell': self.properties,
            'effect': self,
        }]

    # --- effect marker ---------------------------------------------------------

    @staticmethod
    def maze(entity, opts=None):
        return True

    # --- zone plumbing ----------------------------------------------------------

    def zone(self, battle=None):
        from natural20.utils.pocket_dimension import (
            PocketDimensionZone, find_pocket_zone)
        for entry in list(getattr(self.source, 'casted_effects', None) or []):
            if isinstance(entry, dict) and entry.get('effect') is self:
                target = entry.get('target')
                if isinstance(target, PocketDimensionZone) and not getattr(target, '_dismissed', False):
                    return target
        session = getattr(self.source, 'session', None) or self.session
        if session is None:
            return None
        return find_pocket_zone(
            session,
            zone_id=getattr(self, 'zone_id', '') or None,
            map_name=getattr(self, 'pocket_map_name', '') or None,
            battle=battle,
        )

    def members(self):
        session = getattr(self.source, 'session', None) or self.session
        out = []
        for uid in [u for u in str(self.target_uid or '').split(',') if u]:
            member = session.entity_by_uid(uid) if session is not None else None
            if member is not None:
                out.append(member)
        return out

    # --- apply -------------------------------------------------------------------

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'maze':
            return None
        from natural20.utils.pocket_dimension import (
            create_pocket_dimension, maze_map_properties)
        from natural20.map_set import place_entity_instance

        source, target, effect = item['source'], item['target'], item['effect']
        session = session or (battle.session if battle is not None
                              else source.session)
        battle_map = (battle.map_for(target) if battle is not None
                      else session.map_for(target))
        if battle_map is None:
            return None
        try:
            return_square = list(battle_map.position_of(target))
        except Exception:
            return_square = None

        props = effect.properties or {}
        duration = int(props.get('duration_seconds', 600) or 600)
        cells = props.get('maze_cells') or [8, 8]
        map_props, entrance_xy, warden_xy = maze_map_properties(
            cells_x=int(cells[0]), cells_y=int(cells[1]),
            feet_per_grid=getattr(battle_map, 'feet_per_grid', 5) or 5,
            label=props.get('pocket_label') or 'The Labyrinth',
            narration=props.get('pocket_narration') or '',
            illumination=float(props.get('pocket_illumination', 0.3) or 0.3),
        )

        zone = create_pocket_dimension(
            session, source, battle, battle_map,
            return_square or battle_map.position_of(source),
            name='maze',
            label=props.get('pocket_label') or 'The Labyrinth',
            capacity=8,
            duration_seconds=duration,
            illumination=float(props.get('pocket_illumination', 0.3) or 0.3),
            token_image=None,
            narration=props.get('pocket_narration') or '',
            map_properties=map_props,
            climbable=False,
            inner_entrance_pos=entrance_xy,
            spell=effect,
        )
        zone.return_square = list(return_square) if return_square else None
        effect.zone_id = zone.id
        effect.pocket_map_name = zone.pocket_map_name
        effect.target_uid = target.entity_uid

        # Banish the target: member effect (grants the escape action) + move.
        source.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + duration})
        target.register_effect('maze', MazeSpell, effect=effect,
                               source=source, duration=duration)
        zone.enter(target, battle, emit=False)

        # The maze's minotaur: part of the space, not a member — it vanishes
        # when the demiplane collapses (PocketDimensionZone.on_dismiss).
        warden_kind = props.get('maze_npc') or 'minotaur'
        pocket = zone.pocket_map()
        warden = None
        if warden_kind and pocket is not None:
            try:
                warden = session.npc(warden_kind, {'rand_life': True})
            except Exception:
                warden = None
        if warden is not None:
            session.register_entity(warden)
            place_entity_instance(session, warden, pocket,
                                  warden_xy[0], warden_xy[1], group='b')
            effect.warden_uid = getattr(warden, 'entity_uid', '')

        # Owner-side entry targeting the zone: Dispel Magic routing.
        source.add_casted_effect({'target': zone, 'effect': effect,
                                  'expiration': session.game_time + duration})

        # Concentration (caster is on the outer map; the zone also self-expires
        # after duration_seconds even if the tick happens mid-exploration).
        if source.current_concentration() != effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'maze_trapped',
            'source': source,
            'target': target,
            'warden': getattr(warden, 'name', None) if warden else None,
            'map': zone.pocket_map_name,
            'zone_id': zone.id,
        })
        return target

    def dismiss(self, entity, _descriptor=None, opts=None):
        """Concentration broken / dismissed / dispelled: collapse the maze."""
        zone = self.zone()
        if zone is not None and not getattr(zone, '_dismissed', False):
            zone.dismiss('dismissed')
            return
        # Zone already gone: plain effect cleanup.
        for member in self.members():
            effects = member.effects.get('maze') or []
            kept = [f for f in effects if f.get('effect') is not self]
            if kept:
                member.effects['maze'] = kept
            else:
                member.effects.pop('maze', None)
