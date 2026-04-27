"""Engine support for the 5e Ready (a.k.a. Hold) action.

A ``ReadyActionState`` represents a creature that has spent its action on
its turn to declare a *trigger* and a *prepared action* (or move). When the
trigger fires the creature spends its reaction to take that action.

The webapp drives this end-to-end with an LLM, but the engine itself only
needs a small data class plus a couple of helpers so that ``Battle`` can
store and dispatch readied actions in a save/load-safe way. Higher level
resolvers (LLM-assisted in the webapp, deterministic in tests) plug into
``Battle`` by registering a callable through
``Battle.set_ready_action_resolver``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Callable

# Recognised trigger event names. We deliberately keep this list small for
# the v1 implementation; new triggers can be added incrementally.
SUPPORTED_TRIGGER_EVENTS = (
    'movement',           # Any creature finishes a move
    'start_of_turn',      # A creature's turn begins
    'attacked',           # The readying creature is attacked (future hook)
    'becomes_visible',    # A creature enters the readier's line of sight
                          # (synthesised from movement events; see
                          # Battle._dispatch_readied_actions)
    'goes_down',          # A creature drops to 0 HP / falls unconscious or
                          # dies. Synthesised by Battle from event_manager
                          # 'unconscious' and 'died' events. Subject filter
                          # defaults to 'enemies'; pass 'allies' to react to
                          # a friend dropping (e.g. ready a healing potion).
    'on_command',         # An ally (or any speaker matching subject_filter)
                          # utters a recognised command word/phrase. Fired
                          # by the conversation pipeline when a battle is
                          # active. Use ``trigger['command_phrase']`` to set
                          # the substring to look for (case-insensitive).
    'object_interaction', # An object is interacted with -- typically a door
                          # opening/closing/being unlocked. Synthesised from
                          # event_manager 'object_interaction' events. Use
                          # ``trigger['object_action']`` (e.g. 'open',
                          # 'close', 'unlock') to scope the match.
    'ally_attacks',       # An ally makes an attack (weapon attack or attack
                          # spell). Subject filter defaults to 'allies' so
                          # the readier reacts to friendly attackers. Use
                          # ``trigger['attack_target_uid']`` to scope to a
                          # specific enemy. The default attack resolver will
                          # auto-target the same enemy the ally just hit.
)

# Recognised prepared-action kinds. ``attack`` and ``dodge`` are honoured by
# the deterministic fallback resolver bundled below; ``spell`` and ``move``
# are exposed structurally so the LLM resolver can implement them.
SUPPORTED_ACTION_KINDS = (
    'attack', 'spell', 'move', 'use_item',
)


class HeldSpellEffect:
    """Marker concentration effect for a readied spell.

    Per 5e RAW, *holding onto the spell's magic requires concentration. If
    your concentration is broken, the spell dissipates without taking
    effect.* This object is what the readier concentrates on while the
    spell is held; ``Battle._install_concentration_break_bridge`` watches
    for ``concentration_end`` events and expires the matching readied
    state when the effect drops.

    Attributes mirror the minimal surface other concentration effects use
    (``label``, ``concentration_save_dc``, ``concentration_auto_break``)
    so the existing damage-time concentration check works unmodified.
    """

    __slots__ = ('owner_uid', 'spell_slug', 'label_text',
                 'concentration_save_dc', 'concentration_auto_break',
                 'is_held_spell')

    def __init__(self, owner_uid: str, spell_slug: str):
        self.owner_uid = str(owner_uid)
        self.spell_slug = str(spell_slug)
        self.label_text = f"Holding {spell_slug.replace('_', ' ').title()}"
        self.concentration_save_dc = None
        self.concentration_auto_break = True
        self.is_held_spell = True

    def label(self):
        return self.label_text

    def __repr__(self):  # pragma: no cover - debug only
        return f"HeldSpellEffect({self.spell_slug} held by {self.owner_uid})"


@dataclass
class ReadyActionState:
    """Persistent record of a single readied action.

    All fields are JSON-friendly so the state survives ``Battle.to_dict``
    round-trips. Live entity references are looked up by UID at fire time.
    """

    entity_uid: str
    description: str = ''
    trigger: Dict[str, Any] = field(default_factory=dict)
    action_spec: Dict[str, Any] = field(default_factory=dict)
    declared_round: int = 0
    concentration_required: bool = False
    expired: bool = False
    fire_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReadyActionState':
        return cls(
            entity_uid=str(data.get('entity_uid', '')),
            description=str(data.get('description', '') or ''),
            trigger=dict(data.get('trigger') or {}),
            action_spec=dict(data.get('action_spec') or {}),
            declared_round=int(data.get('declared_round', 0) or 0),
            concentration_required=bool(data.get('concentration_required', False)),
            expired=bool(data.get('expired', False)),
            fire_count=int(data.get('fire_count', 0) or 0),
        )


def _entity_position(battle, entity):
    if entity is None:
        return None
    try:
        return battle.entity_or_object_pos(entity)
    except Exception:
        return None


def _grid_distance_ft(battle, a, b) -> Optional[float]:
    """Best-effort Chebyshev distance in feet between two entities."""
    if a is None or b is None:
        return None
    pos_a = _entity_position(battle, a)
    pos_b = _entity_position(battle, b)
    if pos_a is None or pos_b is None:
        return None
    map_obj = None
    try:
        map_obj = battle.map_for(a) or battle.map_for(b)
    except Exception:
        map_obj = None
    feet_per = getattr(map_obj, 'feet_per_grid', 5) if map_obj is not None else 5
    dx = abs(pos_a[0] - pos_b[0])
    dy = abs(pos_a[1] - pos_b[1])
    return max(dx, dy) * feet_per


def _subjects_match(state: ReadyActionState, battle, source, owner) -> bool:
    """Return True if ``source`` matches the trigger's subject filter."""
    trigger = state.trigger or {}
    subject_uids = trigger.get('subject_uids') or []
    if subject_uids:
        return getattr(source, 'entity_uid', None) in {str(u) for u in subject_uids}

    subject_filter = (trigger.get('subject_filter') or 'enemies').lower()
    if subject_filter == 'all' or subject_filter == 'any':
        return True
    if owner is None or source is None or source is owner:
        return False
    if subject_filter == 'self':
        return source is owner
    try:
        same_group = battle.allies(owner, source)
    except Exception:
        same_group = False
    if subject_filter == 'allies':
        return bool(same_group)
    # default: enemies
    return not bool(same_group)


def evaluate_trigger(state: ReadyActionState, event_name: str,
                     event_payload: Dict[str, Any], battle, owner) -> bool:
    """Return True if ``event_name`` should fire this readied action."""
    if state is None or state.expired:
        return False
    trigger = state.trigger or {}
    expected_event = (trigger.get('event') or '').lower()
    if expected_event and expected_event != event_name:
        return False

    source = (event_payload or {}).get('source') if isinstance(event_payload, dict) else None
    target = (event_payload or {}).get('target') if isinstance(event_payload, dict) else None
    # Some battle events use ``source`` as the trigger object; others put the
    # acting creature in ``target`` (e.g. ``start_of_turn``).
    actor = source if source is not None else target

    if not _subjects_match(state, battle, actor, owner):
        return False

    # For ``attacked`` triggers, also require the readier to be the target of
    # the attack (or in the explicit subject_uids list). Without this, an
    # attack between two unrelated creatures would fire every "when attacked"
    # ready action on the field.
    if event_name == 'attacked':
        subject_uids = trigger.get('subject_uids') or []
        if subject_uids:
            # already filtered by _subjects_match
            pass
        else:
            if target is None or target is not owner:
                return False

    # ``becomes_visible`` is dispatched by ``Battle._dispatch_readied_actions``
    # only after it has confirmed the visibility transition. Range/condition
    # filters below still apply (e.g. "fire only if within 60 ft").

    if event_name == 'on_command':
        # The spoken text comes in via payload['message']; an optional
        # explicit recipients list is in payload['targets']. If the readier
        # is not addressed (and the trigger had no broader subject_uids), we
        # still allow it to fire when the speaker is in subject_filter scope
        # so a familiar can react to its master's command even when the
        # master is technically addressing a third party.
        phrase = (trigger.get('command_phrase') or '').strip().lower()
        if phrase:
            spoken = ''
            if isinstance(event_payload, dict):
                spoken = str(event_payload.get('message') or '').lower()
            if phrase not in spoken:
                return False

    if event_name == 'object_interaction':
        wanted_action = (trigger.get('object_action') or '').strip().lower()
        if wanted_action:
            sub_type = ''
            if isinstance(event_payload, dict):
                sub_type = str(event_payload.get('sub_type') or '').lower()
            if sub_type != wanted_action:
                return False
        # Optional: scope to a specific object by its entity_uid.
        wanted_uid = str(trigger.get('object_uid') or '').strip()
        if wanted_uid:
            obj = (event_payload or {}).get('target') if isinstance(event_payload, dict) else None
            obj_uid = str(getattr(obj, 'entity_uid', '') or '')
            if obj_uid != wanted_uid:
                return False

    if event_name == 'ally_attacks':
        # Optionally scope to a specific enemy being attacked. If unset, any
        # enemy target counts (as long as the attacker matches subject_filter
        # already enforced above). The readier should not react to its own
        # attacks, but ``_subjects_match`` already filters out source==owner.
        wanted_target_uid = str(trigger.get('attack_target_uid') or '').strip()
        if wanted_target_uid:
            target_uid = str(getattr(target, 'entity_uid', '') or '')
            if target_uid != wanted_target_uid:
                return False

    condition = (trigger.get('condition') or 'always').lower()
    if condition == 'always':
        return True
    if condition == 'starts_turn':
        return event_name == 'start_of_turn'
    if condition == 'adjacent_to_self':
        # 5 ft (one square) distance using Chebyshev metric.
        dist = _grid_distance_ft(battle, owner, actor)
        return dist is not None and dist <= 5
    if condition == 'within_range':
        try:
            range_ft = float(trigger.get('range_ft', 5))
        except Exception:
            range_ft = 5.0
        dist = _grid_distance_ft(battle, owner, actor)
        return dist is not None and dist <= range_ft
    # Unknown conditions are treated as "always" so the LLM is never silently
    # ignored if it picks a condition we don't understand yet; the resolver
    # can still reject the firing.
    return True


def normalize_trigger(raw: Any) -> Dict[str, Any]:
    """Validate/normalise an LLM-provided trigger blob.

    Unknown values are coerced to safe defaults so the engine never trips on
    malformed input, but the original is preserved in ``description``.
    """
    if not isinstance(raw, dict):
        raw = {}
    event = str(raw.get('event') or 'movement').lower()
    if event not in SUPPORTED_TRIGGER_EVENTS:
        event = 'movement'
    condition = str(raw.get('condition') or 'always').lower()
    # Default subject filter depends on the event: 'allies' for events that
    # describe a friendly trigger ('goes_down', 'on_command', 'ally_attacks'),
    # 'enemies' otherwise.
    default_subject = 'enemies'
    if event in ('goes_down', 'on_command', 'ally_attacks'):
        default_subject = 'allies'
    subject_filter = str(raw.get('subject_filter') or default_subject).lower()
    if subject_filter not in ('all', 'any', 'self', 'allies', 'enemies'):
        subject_filter = 'enemies'
    subject_uids = [str(u) for u in (raw.get('subject_uids') or []) if u is not None]
    try:
        range_ft = int(raw.get('range_ft') or 5)
    except Exception:
        range_ft = 5
    description = str(raw.get('description') or '').strip()
    command_phrase = str(raw.get('command_phrase') or '').strip()
    object_action = str(raw.get('object_action') or '').strip().lower()
    object_uid = str(raw.get('object_uid') or '').strip()
    attack_target_uid = str(raw.get('attack_target_uid') or '').strip()
    return {
        'event': event,
        'condition': condition,
        'subject_filter': subject_filter,
        'subject_uids': subject_uids,
        'range_ft': max(0, range_ft),
        'description': description,
        'command_phrase': command_phrase,
        'object_action': object_action,
        'object_uid': object_uid,
        'attack_target_uid': attack_target_uid,
    }


def normalize_action_spec(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    kind = str(raw.get('kind') or 'attack').lower()
    if kind not in SUPPORTED_ACTION_KINDS:
        kind = 'attack'
    spec: Dict[str, Any] = {
        'kind': kind,
        'description': str(raw.get('description') or '').strip(),
    }
    if kind == 'attack':
        spec['weapon'] = str(raw.get('weapon') or '').strip() or None
        target = raw.get('target')
        spec['target_uid'] = str(target).strip() if target else None
    elif kind == 'spell':
        spec['spell'] = str(raw.get('spell') or '').strip() or None
        try:
            spec['at_level'] = int(raw.get('at_level') or 0) or None
        except Exception:
            spec['at_level'] = None
        target = raw.get('target')
        spec['target_uid'] = str(target).strip() if target else None
    elif kind == 'move':
        spec['direction'] = str(raw.get('direction') or 'away').lower()
        target = raw.get('target')
        spec['target_uid'] = str(target).strip() if target else None
    elif kind == 'use_item':
        # ``item`` is the inventory slug (e.g. 'healing_potion'). ``target_uid``
        # is the recipient (defaults to the trigger actor at fire time, e.g.
        # the ally who just dropped to 0 HP).
        spec['item'] = str(raw.get('item') or raw.get('weapon') or '').strip() or None
        target = raw.get('target')
        spec['target_uid'] = str(target).strip() if target else None
    return spec


# --------------------------------------------------------------------------
# Default deterministic resolver. Used by tests and as a safe fallback when
# no LLM resolver is registered. Handles attack-by-weapon-name and dodge.
# --------------------------------------------------------------------------

ResolverCallable = Callable[
    ['ReadyActionState', str, Dict[str, Any], Any, Any],  # state, event_name, event_payload, battle, owner
    Optional[Any],  # returns an Action ready to execute, or None to skip
]


def _set_reason(state: ReadyActionState, reason: str) -> None:
    try:
        setattr(state, 'last_fizzle_reason', reason)
    except Exception:
        pass


def default_resolver(state: ReadyActionState, event_name: str,
                     event_payload: Dict[str, Any], battle, owner):
    """Return an executable Action for the readied state, or None.

    On ``None`` returns, the resolver records a human-readable explanation in
    ``state.last_fizzle_reason`` so the battle log can surface why a readied
    action did not fire.
    """
    spec = state.action_spec or {}
    kind = (spec.get('kind') or '').lower()

    payload = event_payload or {}
    trigger_source = payload.get('source') if isinstance(payload, dict) else None
    trigger_target = payload.get('target') if isinstance(payload, dict) else None
    trigger_actor = trigger_source if trigger_source is not None else trigger_target
    # For ``ally_attacks``, the natural follow-up target is the *enemy* the
    # ally just struck (payload['target']), not the ally themselves. Prefer
    # that as the auto-targeting fallback unless the spec pins a target_uid.
    if event_name == 'ally_attacks' and trigger_target is not None:
        trigger_actor = trigger_target

    if kind == 'attack':
        # Choose target: explicit override, else the entity that triggered us.
        target = None
        target_uid = spec.get('target_uid')
        if target_uid:
            try:
                target = battle.session.entity_registry.get(str(target_uid))
            except Exception:
                target = None
        if target is None:
            target = trigger_actor
        if target is None or target is owner:
            _set_reason(state, 'no valid target (would be self or empty)')
            return None
        # Build a plain melee/ranged attack with the requested weapon. We use
        # ``opportunity_attack=True`` so AttackAction.can validates against
        # reaction availability rather than action availability.
        from natural20.actions.attack_action import AttackAction
        if not AttackAction.can(owner, battle, {'opportunity_attack': True}):
            _set_reason(state, 'no reaction available')
            return None
        weapon_slug = spec.get('weapon') or None
        # Verify the weapon is currently equipped, and pre-check range/reach
        # so the log explains an out-of-reach miss instead of a generic
        # 'no attack option' message.
        try:
            equipped = list(owner.equipped_weapons(battle.session)) if hasattr(owner, 'equipped_weapons') else []
        except Exception:
            equipped = []
        if weapon_slug and equipped and weapon_slug not in equipped:
            _set_reason(state, f"weapon '{weapon_slug}' is not currently equipped (equipped: {equipped})")
            return None
        try:
            weapon_def = battle.session.load_weapon(weapon_slug) if weapon_slug else None
        except Exception:
            weapon_def = None
        if weapon_def is not None:
            try:
                map_ = battle.map_for(owner)
                if map_ is not None:
                    distance_ft = map_.distance(owner, target) * map_.feet_per_grid
                    weapon_type = (weapon_def.get('type') or '').lower()
                    if weapon_type == 'ranged_attack':
                        rng = weapon_def.get('range') or weapon_def.get('range_max') or 5
                        try:
                            rng = int(rng)
                        except Exception:
                            rng = 5
                        if distance_ft > rng:
                            _set_reason(
                                state,
                                f"target out of range ({int(distance_ft)} ft > {rng} ft for {weapon_slug})",
                            )
                            return None
                    else:
                        reach_ft = int(weapon_def.get('reach') or 5)
                        if distance_ft > reach_ft:
                            _set_reason(
                                state,
                                f"target out of reach ({int(distance_ft)} ft > {reach_ft} ft for {weapon_slug})",
                            )
                            return None
            except Exception:
                pass
        try:
            available = owner.available_actions(
                battle.session, battle, opportunity_attack=True,
                map=battle.map_for(owner), auto_target=False,
            )
        except Exception:
            available = []
        attack_action = None
        for candidate in available:
            if not isinstance(candidate, AttackAction):
                continue
            if weapon_slug and getattr(candidate, 'using', None) != weapon_slug:
                continue
            attack_action = candidate
            break
        if attack_action is None:
            # Fall back to the first attack option if the requested weapon is
            # not currently equipped.
            for candidate in available:
                if isinstance(candidate, AttackAction):
                    attack_action = candidate
                    break
        if attack_action is None:
            if weapon_slug:
                _set_reason(state, f"no attack option matching weapon '{weapon_slug}' is currently available")
            else:
                _set_reason(state, 'no attack options are currently available')
            return None
        attack = attack_action.clone()
        attack.target = target
        attack.as_reaction = True
        return attack

    if kind == 'spell':
        spell_slug = (spec.get('spell') or '').strip()
        if not spell_slug:
            _set_reason(state, 'readied spell had no spell slug recorded')
            return None
        target = None
        target_uid = spec.get('target_uid')
        if target_uid:
            try:
                target = battle.session.entity_registry.get(str(target_uid))
            except Exception:
                target = None
        if target is None:
            target = trigger_actor
        if target is None or target is owner:
            _set_reason(state, 'no valid target for the readied spell (would be self or empty)')
            return None
        if not owner.has_reaction(battle):
            _set_reason(state, 'no reaction available')
            return None
        from natural20.actions.spell_action import SpellAction
        slot_pre_consumed = bool(spec.get('_slot_pre_consumed'))
        # NOTE: ``SpellAction.can_cast`` validates the spell's listed
        # casting_time resource (usually "action"), which will always be 0
        # outside the caster's own turn. Readied spells are cast as the
        # entity's reaction instead, so we run a reaction-aware variant of
        # the same checks here.
        try:
            spell_details = battle.session.load_spell(spell_slug)
            if not spell_details:
                _set_reason(state, f"spell '{spell_slug}' is not defined in the spell list")
                return None
            spell_level = int(spell_details.get('level', 0) or 0)
            slot_owner = owner.owner if owner.familiar() else owner
            # Slot availability + per-turn cap apply only when the slot was
            # NOT already paid at ready time (legacy code path / LLM-built
            # held spells that bypassed ``prepare_held_spell``).
            if not slot_pre_consumed and spell_level > 0:
                has_slot = False
                at_level_check = at_level if (at_level := spec.get('at_level')) else spell_level
                try:
                    at_level_check = int(at_level_check)
                except Exception:
                    at_level_check = spell_level
                for spell_class in spell_details.get('spell_list_classes', []):
                    class_key = spell_class.lower()
                    if hasattr(slot_owner, 'next_spell_slot_level'):
                        if slot_owner.next_spell_slot_level(class_key, at_level_check) is not None:
                            has_slot = True
                            break
                    elif slot_owner.spell_slots_count(at_level_check, class_key) > 0:
                        has_slot = True
                        break
                if not has_slot:
                    _set_reason(state, f"no available spell slot for {spell_slug} (level {at_level_check})")
                    return None
                # Already-cast-leveled-spell-this-turn rule still applies even
                # when casting as a reaction: a leveled readied spell is blocked
                # if a leveled spell was cast on the previous turn. (When
                # the slot was pre-consumed, the cast was already counted at
                # ready time, so re-checking here would double-count.)
                if owner.casted_leveled_spells(battle) > 0:
                    _set_reason(state, 'already cast a leveled spell this turn (cannot cast another)')
                    return None
        except Exception as exc:
            _set_reason(state, f"pre-cast checks raised: {exc}")
            return None
        # Range pre-check using the spell template, before invoking the
        # spell-specific build_map (which may raise on out-of-range).
        try:
            spell_def = battle.session.load_spell(spell_slug) or {}
            spell_range = spell_def.get('range')
            if spell_range is not None and target is not None:
                map_ = battle.map_for(owner)
                if map_ is not None:
                    distance_ft = map_.distance(owner, target) * map_.feet_per_grid
                    if distance_ft > int(spell_range):
                        _set_reason(
                            state,
                            f"target out of range ({int(distance_ft)} ft > {int(spell_range)} ft for {spell_slug})",
                        )
                        return None
        except Exception:
            # Range check is best-effort; let the build path surface real errors.
            pass
        try:
            outer = SpellAction.build(battle.session, owner)
            at_level_raw = spec.get('at_level')
            try:
                at_level = int(at_level_raw) if at_level_raw else None
            except Exception:
                at_level = None
            inner = outer['next']((spell_slug, at_level))
            if isinstance(inner, dict) and callable(inner.get('next')):
                final_action = inner['next'](target)
            elif hasattr(inner, 'target'):
                final_action = inner
                final_action.target = target
            else:
                _set_reason(state, f"could not build a target step for spell {spell_slug}")
                return None
        except Exception as exc:
            _set_reason(state, f"failed to build {spell_slug} action: {exc}")
            return None
        if final_action is None:
            _set_reason(state, f"spell builder returned no action for {spell_slug}")
            return None
        try:
            final_action.as_reaction = True
        except Exception:
            pass
        if slot_pre_consumed:
            # Slot + casted-this-turn tally were paid at ready time. Tell
            # SpellAction to skip its built-in consume step so we don't
            # double-charge.
            try:
                final_action.skip_consume_at_resolve = True
            except Exception:
                pass
            # Releasing the held magic ends the held-spell concentration
            # (the spell is no longer being held). Drop only if the current
            # concentration is the held-spell marker; if the readier has
            # already started concentrating on something else (e.g. their
            # held spell broke and they cast something new), leave it alone.
            current = getattr(owner, 'concentration', None)
            if current is not None and getattr(current, 'is_held_spell', False) \
                    and getattr(current, 'spell_slug', None) == spell_slug:
                try:
                    owner.drop_concentration()
                except Exception:
                    pass
        return final_action

    if kind == 'use_item':
        # Ready a usable item (healing potion, scroll, etc.) on a target.
        item_slug = (spec.get('item') or '').strip()
        if not item_slug:
            _set_reason(state, 'readied use_item had no item slug recorded')
            return None
        target = None
        target_uid = spec.get('target_uid')
        if target_uid:
            try:
                target = battle.session.entity_registry.get(str(target_uid))
            except Exception:
                target = None
        if target is None:
            target = trigger_actor
        if target is None:
            # Self-administered consumables (e.g. potion of healing on the
            # readier itself) are valid; only bail if we have no entity at all.
            target = owner
        if not owner.has_reaction(battle):
            _set_reason(state, 'no reaction available')
            return None
        try:
            inventory = getattr(owner, 'inventory', None) or {}
            qty = (inventory.get(item_slug) or {}).get('qty', 0) if isinstance(inventory, dict) else 0
        except Exception:
            qty = 0
        if not qty or qty <= 0:
            _set_reason(state, f"item '{item_slug}' is not in {getattr(owner, 'name', 'owner')}'s inventory")
            return None
        try:
            item_details = battle.session.load_equipment(item_slug)
        except Exception:
            item_details = None
        if not item_details or not item_details.get('usable'):
            _set_reason(state, f"item '{item_slug}' is not a usable item")
            return None
        # Range guard: the item's build_map typically restricts to range 5 ft
        # for healing potions. Reject early so the log explains the miss
        # instead of failing inside ``build_next``.
        try:
            map_ = battle.map_for(owner)
            if map_ is not None and target is not owner:
                distance_ft = map_.distance(owner, target) * map_.feet_per_grid
                if distance_ft > 5:
                    _set_reason(
                        state,
                        f"target out of reach ({int(distance_ft)} ft > 5 ft for {item_slug})",
                    )
                    return None
        except Exception:
            pass
        from natural20.actions.use_item_action import UseItemAction
        try:
            outer = UseItemAction.build(battle.session, owner)
            inner = outer['next'](item_slug)
            if isinstance(inner, dict) and callable(inner.get('next')):
                final_action = inner['next'](target)
            elif hasattr(inner, 'target'):
                final_action = inner
                final_action.target = target
            else:
                _set_reason(state, f"could not build use_item step for {item_slug}")
                return None
        except Exception as exc:
            _set_reason(state, f"failed to build use_item action for {item_slug}: {exc}")
            return None
        if final_action is None:
            _set_reason(state, f"use_item builder returned no action for {item_slug}")
            return None
        # Mark as a reaction so ``UseItemAction.apply`` consumes the
        # readier's reaction instead of (a non-existent) action this turn.
        try:
            final_action.as_reaction = True
        except Exception:
            pass
        return final_action

    # Held moves are not handled by the default resolver. The webapp registers
    # a richer LLM-backed resolver for these cases.
    _set_reason(state, f"no default resolver implementation for kind '{kind or 'unknown'}'")
    return None


def prepare_held_spell(battle, owner, spec):
    """Validate + commit the up-front cost of readying a spell.

    Per 5e RAW (PHB p.193, "Ready"):

        When you ready a spell, you cast it as normal but hold its energy,
        which you release with your reaction when the trigger occurs. To be
        readied, a spell must have a casting time of 1 action, and holding
        onto the spell's magic requires concentration. If your concentration
        is broken, the spell dissipates without taking effect.

    Returns ``(effect, error)`` -- on success ``effect`` is the
    :class:`HeldSpellEffect` placed on the readier (already concentrated
    on); ``error`` is ``None``. On failure ``effect`` is ``None`` and
    ``error`` is a human-readable string.

    Side effects on success:
      * Validates the spell's ``casting_time`` is ``1:action``.
      * Validates the readier has an available slot of the requested level.
      * Drops any prior concentration (RAW: starting a new concentration
        spell ends the previous one).
      * Calls ``Entity.consume_spell_slot`` to expend the slot now.
      * Appends to ``battle.entity_state_for(owner)['casted_level_spells']``
        so the "no two leveled spells in one turn" guard remains accurate.
      * Begins concentration on a :class:`HeldSpellEffect` marker.
    """
    if battle is None or owner is None or not isinstance(spec, dict):
        return None, 'invalid arguments'
    spell_slug = (spec.get('spell') or '').strip()
    if not spell_slug:
        return None, 'no spell slug recorded'
    try:
        details = battle.session.load_spell(spell_slug)
    except Exception as exc:
        return None, f"could not load spell '{spell_slug}': {exc}"
    if not details:
        return None, f"spell '{spell_slug}' is not defined"
    casting_time = str(details.get('casting_time') or '').strip().lower()
    # RAW: only 1-action spells can be readied.
    if casting_time and casting_time != '1:action':
        return None, (
            f"spell '{spell_slug}' has casting_time '{casting_time}'; only "
            "1-action spells can be readied"
        )
    spell_level = int(details.get('level', 0) or 0)
    at_level_raw = spec.get('at_level')
    try:
        at_level = int(at_level_raw) if at_level_raw else spell_level
    except Exception:
        at_level = spell_level
    slot_owner = owner.owner if owner.familiar() else owner
    casting_class = None
    if spell_level > 0:
        has_slot = False
        for spell_class in details.get('spell_list_classes', []):
            class_key = spell_class.lower()
            if hasattr(slot_owner, 'next_spell_slot_level'):
                slot_level = slot_owner.next_spell_slot_level(class_key, at_level)
                if slot_level is not None:
                    has_slot = True
                    casting_class = class_key
                    at_level = slot_level
                    break
            elif slot_owner.spell_slots_count(at_level, class_key) > 0:
                has_slot = True
                casting_class = class_key
                break
        if not has_slot:
            return None, f"no available spell slot for {spell_slug} (level {at_level})"
    # Drop existing concentration (RAW: starting a new concentration spell
    # ends the previous one).
    if getattr(owner, 'concentration', None) is not None:
        try:
            owner.drop_concentration()
        except Exception:
            pass
    # Pay the slot up front. Cantrips (level 0) do not consume a slot.
    if spell_level > 0:
        try:
            slot_owner.consume_spell_slot(at_level, character_class=casting_class)
        except Exception as exc:
            return None, f"failed to consume spell slot: {exc}"
        # Record the cast so the per-turn "two leveled spells" rule still
        # behaves: the readier has now cast a leveled spell on this turn.
        try:
            entry = dict(details)
            entry['_held'] = True
            battle.entity_state_for(owner)['casted_level_spells'].append(entry)
        except Exception:
            pass
    # Annotate the spec so the resolver knows not to charge the slot again
    # and which class slot was paid (in case the spec was loose).
    spec['_slot_pre_consumed'] = True
    spec['at_level'] = at_level
    if casting_class:
        spec['spellcasting_class'] = casting_class
    # Begin concentration on the held-spell marker.
    effect = HeldSpellEffect(getattr(owner, 'entity_uid', '') or '', spell_slug)
    try:
        battle.start_concentration(owner, effect, save_dc=None, auto_break=True)
    except Exception:
        # Fall back to direct entity API if Battle helper isn't available.
        try:
            owner.concentration_on(effect)
        except Exception:
            pass
    return effect, None


__all__ = [
    'ReadyActionState',
    'HeldSpellEffect',
    'SUPPORTED_TRIGGER_EVENTS',
    'SUPPORTED_ACTION_KINDS',
    'evaluate_trigger',
    'normalize_trigger',
    'normalize_action_spec',
    'default_resolver',
    'prepare_held_spell',
]
