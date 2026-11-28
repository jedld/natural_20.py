"""Teleport — 7th-level conjuration (SRD).

Casters keep a personal database of known destinations
(``natural20.utils.teleport_destinations``); with an empty database the spell
is not castable at all (``requires_known_destination`` gates ``can_cast``).

Casting:
    1. ``select_choice`` — pick one of the caster's known destinations
       (labels carry the familiarity so the DM/player see the risk).
    2. The caster plus up to ``max_creatures`` willing (friendly) creatures
       within ``gather_radius`` feet that the caster can see arrive together
       at the destination.

The DM rolls 1d100 against the PHB Teleportation Outcome table for the
destination's familiarity (``roll_outcome``): Mishap (3d10 force damage to
every teleporting creature, then reroll), Similar Area (nearest map sharing
an ``area_themes`` tag), Off Target (2d12 "miles" in a rolled direction,
modelled as a random spot on the destination's ``off_target_map``), or On
Target. Anchor destinations (a person or object) resolve to the anchor's
*current* position at cast time.
"""
from __future__ import annotations

import random

from natural20.spell.spell import Spell
from natural20.utils.auras import _friendly as friendly
from natural20.utils.teleport_destinations import (
    FAMILIARITY_FALSE,
    FAMILIARITY_LABELS,
    OUTCOME_MISHAP,
    OUTCOME_OFF_TARGET,
    OUTCOME_ON_TARGET,
    OUTCOME_SIMILAR,
    find_destination,
    free_square_near,
    list_destinations,
    normalize_familiarity,
    pick_off_target,
    pick_similar_area,
    resolve_destination,
    roll_outcome,
)

MISHAP_DAMAGE_DICE = 3   # 3d10 force per teleporting creature
MISHAP_DAMAGE_SIDES = 10
MISHAP_MAX_REROLLS = 10
OFF_TARGET_DIRECTIONS = ('east', 'southeast', 'south', 'southwest',
                         'west', 'northwest', 'north', 'northeast')


class TeleportSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.destination_id = ''

    def __str__(self):
        return 'teleport'

    def clone(self):
        spell = super().clone()
        spell.destination_id = self.destination_id
        return spell

    # -- castable options -----------------------------------------------------

    @staticmethod
    def destination_options(entity):
        """``[[label, dest_id], ...]`` for the select_choice step."""
        options = []
        for entry in list_destinations(entity):
            familiarity = normalize_familiarity(entry.get('familiarity'))
            label = f"{entry.get('name')} ({FAMILIARITY_LABELS.get(familiarity, familiarity)})"
            options.append([label, entry.get('id')])
        return options

    def build_map(self, orig_action):
        options = TeleportSpell.destination_options(self.source)
        if not options:
            # Empty destination database: nothing to select, resolve reports
            # the failure (can_cast normally hides the spell entirely).
            action = orig_action.clone()
            action.target = self.source
            return action

        def set_destination(choice):
            action = orig_action.clone()
            action.spell_action.destination_id = choice
            self.destination_id = choice
            action.target = self.source
            return action

        return {
            'param': [
                {
                    'type': 'select_choice',
                    'choices': options,
                    'num': 1,
                }
            ],
            'next': set_destination,
        }

    # -- members ---------------------------------------------------------------

    def members_for(self, entity, battle, battle_map):
        """Caster + up to ``max_creatures`` friendly creatures within
        ``gather_radius`` feet the caster can see (PHB "willing creatures
        you can see within range")."""
        members = [entity]
        if battle_map is None:
            return members
        limit = int(self.properties.get('max_creatures', 8) or 8)
        reach = int(self.properties.get('range', 10) or 10) / (
            getattr(battle_map, 'feet_per_grid', 5) or 5)
        try:
            origin = battle_map.position_of(entity)
        except Exception:
            return members
        nearby = []
        for other in list(battle_map.entities.keys()):
            if other is entity or len(members) + len(nearby) > limit:
                continue
            if getattr(other, 'object', lambda: False)():
                continue
            if not hasattr(other, 'register_effect') or other.dead():
                continue
            if not friendly(entity, other, battle):
                continue
            try:
                if battle_map.distance(entity, other) > reach:
                    continue
                if not battle_map.can_see(entity, other):
                    continue
            except Exception:
                continue
            nearby.append(other)
        members.extend(nearby[:max(0, limit - len(members) + 1)])
        return members

    # -- resolve ---------------------------------------------------------------

    def resolve(self, entity, battle, spell_action, battle_map):
        session = getattr(entity, 'session', None) or self.session
        destination_id = (getattr(spell_action, 'destination_id', None)
                          or getattr(getattr(spell_action, 'spell_action', None),
                                     'destination_id', None)
                          or self.destination_id)
        destination = find_destination(entity, destination_id) if destination_id else None
        members = self.members_for(entity, battle, battle_map)

        if destination is None:
            self._emit(session, {
                'event': 'teleport_failed',
                'source': entity,
                'target': entity,
                'message': ('the spell fizzles — no teleportation destination is known'
                            if not destination_id else
                            'that destination no longer exists'),
            })
            return [{
                'type': 'teleport_failed',
                'source': entity,
                'target': entity,
                'spell': self.properties,
                'reason': 'no_known_destination' if not destination else 'destination_gone',
                'members': members,
            }]

        familiarity = normalize_familiarity(destination.get('familiarity'))
        resolved = resolve_destination(session, entity, destination, battle=battle)
        if resolved is None:
            # The map or anchor is gone: rules-wise this is a false destination.
            familiarity = FAMILIARITY_FALSE

        origin_map = battle.map_for(entity) if battle is not None \
            else getattr(session, 'map_for', lambda _e: None)(entity)

        # The web action route / tests may pin the RNG via opts for
        # deterministic outcomes; normally it is unpredictable like the d100.
        rng = getattr(spell_action, 'teleport_rng', None) or random.Random()
        rolls = []
        outcome = None
        mishap_damage = []
        for _ in range(MISHAP_MAX_REROLLS):
            die = rng.randint(1, 100)
            outcome = roll_outcome(familiarity, die)
            rolls.append({'roll': die, 'outcome': outcome})
            if outcome != OUTCOME_MISHAP:
                break
            dealt = self._apply_mishap(entity, members, battle, session, rng=rng)
            mishap_damage.extend(dealt)
            # "multiple mishaps can occur, dealing damage each time" — reroll.

        arrival = None
        narrative = None
        if outcome == OUTCOME_OFF_TARGET:
            miles = sum(rng.randint(1, 12) for _ in range(2))
            direction = OFF_TARGET_DIRECTIONS[rng.randint(1, 8) - 1]
            narrative = (f"appear {miles} miles away from the destination, "
                         f"in a random direction ({direction})")
            arrival = pick_off_target(session, destination, origin_map, rng=rng) \
                if resolved else None
        elif outcome == OUTCOME_SIMILAR:
            narrative = 'appear in an area visually or thematically similar to the destination'
            arrival = pick_similar_area(session, destination, origin_map, rng=rng) \
                if resolved else None
        if arrival is None and resolved is not None:
            # No authored similar/off-target fallback map: land at the
            # destination itself and keep the outcome narrative in the log.
            arrival = resolved

        if arrival is None:
            self._emit(session, {
                'event': 'teleport_failed',
                'source': entity,
                'target': entity,
                'message': 'the destination dissolves before they arrive',
            })
            return [{
                'type': 'teleport_failed',
                'source': entity,
                'target': entity,
                'spell': self.properties,
                'reason': 'unresolvable_destination',
                'rolls': rolls,
                'members': members,
            }]

        target_map, dest_x, dest_y = arrival
        taken = set()
        moved = []
        for member in members:
            try:
                from_map = battle.map_for(member) if battle is not None \
                    else getattr(session, 'map_for', lambda _e: None)(member)
                from_pos = list(from_map.position_of(member)) if from_map else None
            except Exception:
                from_map, from_pos = None, None
            x, y = free_square_near(target_map, dest_x, dest_y, member, taken=taken)
            taken.add((x, y))
            try:
                from natural20.map_set import place_entity_instance
                place_entity_instance(session, member, target_map, x, y)
            except Exception:
                continue
            moved.append({
                'entity': member,
                'from_map': getattr(from_map, 'name', None),
                'from': from_pos,
                'to': [x, y],
            })

        self._emit(session, {
            'event': 'teleport',
            'source': entity,
            'target': entity,
            'destination': destination.get('name'),
            'familiarity': familiarity,
            'outcome': outcome,
            'rolls': [r['roll'] for r in rolls],
            'members': [m.get('entity').display_name if hasattr(m.get('entity'), 'display_name')
                        else getattr(m.get('entity'), 'name', '?') for m in moved],
            'map': getattr(target_map, 'name', None),
            'narrative': narrative,
            'mishaps': len(rolls) if outcome == OUTCOME_MISHAP or len(rolls) > 1 else None,
        })

        return [{
            'type': 'teleport',
            'source': entity,
            'target': entity,
            'spell': self.properties,
            'members': members,
            'moved': moved,
            'destination': destination.get('name'),
            'destination_id': destination.get('id'),
            'familiarity': familiarity,
            'outcome': outcome,
            'rolls': rolls,
            'to_map': getattr(target_map, 'name', None),
            'to_pos': [dest_x, dest_y],
            'damage': mishap_damage or None,
        }]

    # -- mishap damage ----------------------------------------------------------

    def _apply_mishap(self, entity, members, battle, session, rng=None):
        """3d10 force damage to every teleporting creature (PHB Mishap)."""
        rng = rng or random
        dealt = []
        for member in members:
            dmg = sum(rng.randint(1, MISHAP_DAMAGE_SIDES)
                      for _ in range(MISHAP_DAMAGE_DICE))
            try:
                member.take_damage(dmg, battle=battle, damage_type='force',
                                   session=session)
                dealt.append({'target': member, 'damage': dmg, 'type': 'force'})
            except Exception:
                continue
        return dealt

    def _emit(self, session, payload):
        event_manager = getattr(session, 'event_manager', None)
        if event_manager is None and self.session is not None:
            event_manager = getattr(self.session, 'event_manager', None)
        if event_manager is not None:
            try:
                event_manager.received_event(payload)
            except Exception:
                pass
