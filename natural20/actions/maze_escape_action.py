"""Action: try to escape the Maze spell's labyrinthine demiplane.

The Maze spell registers a ``maze`` effect on the trapped creature. On its
turn the creature can spend an action making the spell's Intelligence check
(DC 20 by default). A success dismisses the pocket dimension, and the zone
teardown expels the creature back onto the square it vanished from.

Creatures listed in the spell YAML ``auto_escape`` (minotaurs and goristras
per the SRD) always succeed — and they know the maze is their home, so the
heuristic AI rates the check very highly.
"""
from natural20.action import Action

EFFECT_KEY = 'maze'


def maze_effects_on(entity):
    """Live ``(effect, source)`` pairs for the ``maze`` effect on ``entity``."""
    out = []
    for entry in (getattr(entity, 'effects', None) or {}).get(EFFECT_KEY, []) or []:
        effect = entry.get('effect')
        expiration = entry.get('expiration')
        session = getattr(entity, 'session', None)
        if expiration is not None and session is not None and expiration <= session.game_time:
            continue
        if effect is not None:
            out.append((effect, entry.get('source')))
    return out


def _auto_escapes(entity, spell_properties):
    from natural20.utils.monster_traits import _creature_types_of
    names = {str(n).lower() for n in (spell_properties or {}).get('auto_escape') or []}
    if not names:
        return False
    return bool(names & set(_creature_types_of(entity)))


class MazeEscapeAction(Action):
    """The trapped creature's DC ``escape_dc`` Intelligence check."""

    def __init__(self, session, source, action_type='maze_escape', opts=None):
        super().__init__(session, source, action_type, opts)
        self.maze_effect = None
        self.zone = None

    # --- availability --------------------------------------------------------

    @staticmethod
    def options_for(session, entity, battle):
        actions = []
        for effect, _source in maze_effects_on(entity):
            zone = effect.zone(battle) if hasattr(effect, 'zone') else None
            if zone is None or zone.expired() or not zone.has_member(entity):
                continue
            action = MazeEscapeAction(session, entity)
            action.maze_effect = effect
            action.zone = zone
            actions.append(action)
        return actions

    @staticmethod
    def can(entity, battle):
        return bool(MazeEscapeAction.options_for(
            getattr(entity, 'session', None), entity, battle))

    def available(self, battle):
        return bool(self.zone is not None and not self.zone.expired()
                    and self.zone.has_member(self.source))

    # --- action plumbing -------------------------------------------------------

    def clone(self):
        action = MazeEscapeAction(self.session, self.source, self.action_type, self.opts)
        action.maze_effect = self.maze_effect
        action.zone = self.zone
        return action

    def build_map(self):
        return {'action': self}

    def ai_value(self, battle):
        props = getattr(self.maze_effect, 'properties', None) or {}
        if _auto_escapes(self.source, props):
            return 10.0
        dc = int(props.get('escape_dc', 20) or 20)
        try:
            mod = int(self.source.ability_mod('int') or 0)
        except Exception:
            mod = 0
        chance = max(0.05, min(0.95, (21 - (dc - mod)) / 20.0))
        # Freedom from the labyrinth is worth a full action every turn.
        return 10.0 * chance

    def resolve(self, session, map=None, opts=None):
        battle = (opts or {}).get('battle')
        self.result = []
        zone = self.zone
        if zone is None:
            # The web /action route instantiates this class fresh: recover the
            # live zone from the maze effect on the source (like
            # BreakFreeAction recomputes its restraint).
            for effect, _source in maze_effects_on(self.source):
                candidate = effect.zone(battle) if hasattr(effect, 'zone') else None
                if candidate is not None and not candidate.expired() and candidate.has_member(self.source):
                    self.maze_effect = effect
                    zone = self.zone = candidate
                    break
        if zone is None or zone.expired():
            return self
        props = getattr(self.maze_effect, 'properties', None) or {}
        dc = int(props.get('escape_dc', 20) or 20)
        auto = _auto_escapes(self.source, props)
        roll = None
        if auto:
            success = True
        else:
            roll = self.source.ability_check(
                'intelligence', battle=battle, description='dice_roll.intelligence')
            success = roll.result() >= dc
        self.result.append({
            'type': 'maze_escape',
            'source': self.source,
            'target': self.source,
            'effect': self.maze_effect,
            'zone_id': zone.id,
            'roll': roll,
            'dc': dc,
            'auto': auto,
            'success': success,
        })
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'maze_escape':
            return None
        session = session or (battle.session if battle is not None
                              else item['source'].session)
        if battle is not None:
            battle.consume(item['source'], 'action')
        if item.get('success'):
            from natural20.utils.pocket_dimension import find_pocket_zone
            zone = find_pocket_zone(session, zone_id=item.get('zone_id'),
                                    battle=battle)
            if zone is not None and not getattr(zone, '_dismissed', False):
                # Teardown clears the maze effect and returns the creature to
                # the square it was banished from (zone.return_square).
                zone.dismiss('escaped')
        session.event_manager.received_event({
            'event': 'maze_escape',
            'source': item['source'],
            'target': item['target'],
            'roll': item.get('roll'),
            'dc': item['dc'],
            'auto': item.get('auto'),
            'success': item['success'],
        })
        return None


from natural20.utils.class_feature_registry import register_class_feature  # noqa: E402

register_class_feature(
    feature_id='maze_escape',
    action_class=MazeEscapeAction,
    provides=lambda entity: bool(maze_effects_on(entity)),
    builder=lambda session, entity, feature_id, battle=None: (
        MazeEscapeAction.options_for(session, entity, battle)),
)
