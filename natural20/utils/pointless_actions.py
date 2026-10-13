"""Drop AI options that are legal but pointless in the current situation.

Applied by the JEV planner and the LLM controller next to the friendly-fire
filter, so decision models never see e.g. Second Wind at full HP, looting
a corpse while an enemy is in sight, or Look when every enemy is visible.
"""
from typing import Any, Callable, Iterable, List, Optional

LOOT_INTERACTIONS = frozenset({'loot', 'pickup_drop', 'take', 'carry', 'give'})


def _hp(entity):
    try:
        return entity.hp(), entity.max_hp()
    except Exception:
        return None, None


def enemies_in_sight(battle, entity) -> bool:
    if battle is None:
        return False
    try:
        opponents = battle.opponents_of(entity)
    except Exception:
        return False
    for opp in opponents:
        try:
            if opp.dead() or not opp.conscious():
                continue
            if battle.can_see(entity, opp):
                return True
        except Exception:
            continue
    return False


def enemies_present(battle, entity) -> bool:
    """A conscious opponent is still in the fight, whether or not *entity*
    can see it (an invisible attacker doesn't make looting safe)."""
    return enemies_in_sight(battle, entity) or bool(conscious_enemies(battle, entity))


def conscious_enemies(battle, entity) -> list:
    """Conscious opponents in the battle, seen or not."""
    if battle is None:
        return []
    try:
        opponents = battle.opponents_of(entity)
    except Exception:
        return []
    out = []
    for opp in opponents:
        try:
            if not opp.dead() and opp.conscious():
                out.append(opp)
        except Exception:
            continue
    return out


def _has_action(battle, entity) -> bool:
    try:
        return entity.total_actions(battle) > 0
    except Exception:
        return False


def knows_an_enemy_position(battle, entity) -> bool:
    """True when *entity* can see an opponent (even a downed one) or senses
    where an unseen one is (heard or last-known square)."""
    if battle is None:
        return True
    try:
        for opp in battle.opponents_of(entity):
            if not opp.dead() and battle.can_see(entity, opp):
                return True
    except Exception:
        return True
    try:
        from natural20.utils.unseen_targets import sensed_creatures
        return bool(sensed_creatures(battle, entity))
    except Exception:
        return True


def look_can_reveal(battle, entity) -> bool:
    """True when an active Perception check (Look) could find someone: a
    conscious opponent that is hidden (Stealth) and not currently seen.
    Invisible-but-not-hidden creatures are already heard at their square,
    and creatures behind walls stay out of sight whatever the roll."""
    if battle is None:
        return True
    for opp in conscious_enemies(battle, entity):
        try:
            if opp.hidden() and not battle.can_see(entity, opp):
                return True
        except Exception:
            return True
    return False


def _distance_ft(battle, a, b):
    battle_map = battle.map_for(a)
    if battle_map is None or battle_map is not battle.map_for(b):
        return None
    return battle_map.distance(a, b) * (getattr(battle_map, 'feet_per_grid', None) or 5)


def threatened_in_melee(battle, entity) -> bool:
    """True when a conscious opponent can reach *entity* with a melee attack."""
    for opp in conscious_enemies(battle, entity):
        try:
            dist = _distance_ft(battle, entity, opp)
            reach = getattr(opp, 'melee_distance', None)
            reach = (reach() if callable(reach) else None) or 5
            if dist is not None and dist <= max(5, reach):
                return True
        except Exception:
            return True
    return False


def _can_move_after(battle, entity) -> bool:
    try:
        if (entity.available_movement(battle) or 0) > 0:
            return True
        return (entity.total_bonus_actions(battle) > 0
                and entity.any_class_feature(['cunning_action', 'nimble_escape']))
    except Exception:
        return True


def _is_loot(action) -> bool:
    from natural20.actions.interact_action import InteractAction
    from natural20.actions.ground_interact_action import GroundInteractAction
    if isinstance(action, GroundInteractAction):
        return True
    if isinstance(action, InteractAction):
        name = action.object_action
        if isinstance(name, (list, tuple)):
            name = name[0] if name else None
        return name in LOOT_INTERACTIONS
    return False


def _pointless_help(battle, entity, action) -> bool:
    """Help on an enemy (distract: an ally's next attack has advantage) is
    useful. Help on an ally only aids its next ability check, which in a
    fight matters just for waking it or escaping a grapple/restraint."""
    target = getattr(action, 'target', None)
    if target is None:
        return False
    if target is entity:
        return True
    if battle is None:
        return False
    try:
        if battle.opposing(entity, target):
            return False
        statuses = getattr(target, 'statuses', None) or []
        return not ('sleep' in statuses or target.grappled() or target.restrained())
    except Exception:
        return False


def _non_combat_spell(action) -> bool:
    """Spell YAML ``ai_in_combat: false`` marks utility spells (Mage Hand,
    Prestidigitation, Comprehend Languages, ...) the AI shouldn't cast mid-fight."""
    spell_action = getattr(action, 'spell_action', None)
    props = getattr(spell_action, 'properties', None)
    if not isinstance(props, dict):
        props = getattr(action, 'spell', None)
    return isinstance(props, dict) and props.get('ai_in_combat') is False


def _recasts_held_concentration(action, entity) -> bool:
    """Spell YAML ``ai_no_recast: true`` (Spirit Guardians, Call Lightning,
    Sleet Storm): recasting while already concentrating on it only burns a
    slot to restart the same effect."""
    spell_action = getattr(action, 'spell_action', None)
    props = getattr(spell_action, 'properties', None)
    held = getattr(entity, 'concentration', None)
    if not isinstance(props, dict) or not props.get('ai_no_recast') or held is None:
        return False
    return bool(props.get('id')) and getattr(held, 'id', None) == props.get('id')


def finishes_downed(entity) -> bool:
    """NPC/PC YAML ``finish_downed: true`` marks a ruthless creature that
    keeps attacking foes already at 0 HP while others are still standing."""
    props = getattr(entity, 'properties', None) or {}
    return bool(props.get('finish_downed', False))


def _downed(creature) -> bool:
    try:
        return not creature.dead() and creature.unconscious()
    except Exception:
        return False


def _spell_props(action) -> dict:
    spell_action = getattr(action, 'spell_action', None)
    props = getattr(spell_action, 'properties', None)
    if not isinstance(props, dict):
        props = getattr(action, 'spell', None)
    return props if isinstance(props, dict) else {}


def _healing_level(action) -> Optional[int]:
    """Spell level of a ``type: healing`` spell option, else ``None``."""
    props = _spell_props(action)
    if str(props.get('type') or '').lower() != 'healing':
        return None
    try:
        return int(props.get('level') or 0)
    except (TypeError, ValueError):
        return 0


def _pointless_hide(battle, entity) -> bool:
    """Hiding again while hidden only rerolls Stealth; hiding in plain view of
    a foe whose passive Perception beats a natural 20 always fails."""
    if 'hidden' in (getattr(entity, 'statuses', None) or []):
        return True
    try:
        best = 20 + int(entity.stealth_mod())
        bmap = battle.map_for(entity)
        obscured = bmap.is_heavily_obscured(entity)
        for foe in conscious_enemies(battle, entity):
            if battle.map_for(foe) is not bmap or not bmap.can_see(foe, entity):
                continue
            perception = (foe.passive_perception() or 0) - (5 if obscured else 0)
            if foe.class_feature('keen_sight_and_smell'):
                perception += 5
            if perception > best:
                return True
    except Exception:
        return False
    return False


def _pointless_dispel(battle, entity, action) -> bool:
    props = _spell_props(action)
    if props.get('id') != 'dispel_magic':
        return False
    from natural20.utils.dispel import creature_target, worth_dispelling
    target = creature_target(getattr(action, 'target', None))
    return not worth_dispelling(battle, entity, target)


def _spare_the_dying_on_non_dying(action) -> bool:
    if _spell_props(action).get('id') != 'spare_the_dying':
        return False
    target = getattr(action, 'target', None)
    from natural20.spell.spare_the_dying_spell import is_dying
    return target is not None and hasattr(target, 'hp') and not is_dying(target)


def _dash_in_melee(battle, entity) -> bool:
    """Dashing while a foe is in reach only buys movement that provokes an
    opportunity attack; Disengage (or attacking) is the better use unless
    the creature is fleeing hurt."""
    try:
        if entity.disengage(battle):
            return False
        hp, max_hp = _hp(entity)
        if hp is not None and max_hp and hp <= max_hp / 2:
            return False
    except Exception:
        return False
    return threatened_in_melee(battle, entity)


def _known_enemy_squares(battle, entity) -> list:
    """Squares of conscious foes *entity* sees, plus heard / last-known
    squares of unseen ones."""
    battle_map = battle.map_for(entity)
    squares = []
    for opp in conscious_enemies(battle, entity):
        try:
            if battle.map_for(opp) is battle_map and battle.can_see(entity, opp):
                pos = battle_map.position_of(opp)
                if pos is not None:
                    squares.append(tuple(pos))
        except Exception:
            continue
    try:
        from natural20.utils.unseen_targets import sensed_creatures
        for entry in sensed_creatures(battle, entity):
            foe = battle.entity_by_uid(entry['uid'])
            if foe is not None and battle.opposing(entity, foe):
                squares.append(tuple(entry['pos']))
    except Exception:
        pass
    return squares


def _dash_without_destination(battle, entity) -> bool:
    """Every known foe is already within this turn's movement (plus reach),
    so the extra movement from Dash has nowhere to go. A hurt creature may
    still Dash to get away."""
    try:
        hp, max_hp = _hp(entity)
        if hp is not None and max_hp and hp <= max_hp / 2:
            return False
        squares = _known_enemy_squares(battle, entity)
        if not squares:
            return False
        battle_map = battle.map_for(entity)
        feet = getattr(battle_map, 'feet_per_grid', None) or 5
        reach = entity.melee_distance() or 5
        movement = entity.available_movement(battle) or 0
        pos = battle_map.position_of(entity)
        for square in squares:
            gap = max(abs(square[0] - pos[0]), abs(square[1] - pos[1])) * feet
            # One square of slack for walls and occupied squares en route.
            if gap - reach > movement - feet:
                return False
        return True
    except Exception:
        return False


def _dash_after_shooting(battle, entity) -> bool:
    """A caster or skirmisher that already spent its action, isn't hurt and
    isn't in melee gets no advance or reposition from the planner, so the
    extra movement has nowhere to go."""
    try:
        if (entity.total_actions(battle) or 0) > 0:
            return False
        hp, max_hp = _hp(entity)
        if hp is not None and max_hp and hp <= max_hp / 2:
            return False
        if threatened_in_melee(battle, entity):
            return False
        from natural20.utils.jev_decision import _ranged_combatant
        return bool(_ranged_combatant(entity)
                    or entity.any_class_feature(['cunning_action', 'nimble_escape']))
    except Exception:
        return False


def is_pointless(battle, entity, action, in_sight=None) -> bool:
    """True when *action* is legal but wasteful for *entity* right now."""
    from natural20.actions.second_wind_action import SecondWindAction
    from natural20.actions.look_action import LookAction
    from natural20.actions.action_surge_action import ActionSurgeAction
    from natural20.actions.disengage_action import DisengageAction
    from natural20.actions.help_action import HelpAction
    from natural20.actions.prone_action import ProneAction
    from natural20.actions.pickpocket_action import PickpocketAction
    from natural20.actions.dash import DashAction
    from natural20.actions.hide_action import HideAction
    from natural20.actions.wrath_of_the_storm_action import WrathOfTheStormAction
    if isinstance(action, SecondWindAction):
        hp, max_hp = _hp(entity)
        return hp is not None and max_hp is not None and hp >= max_hp
    if isinstance(action, LookAction):
        return not look_can_reveal(battle, entity)
    if isinstance(action, DisengageAction):
        return battle is not None and (not threatened_in_melee(battle, entity)
                                       or not _can_move_after(battle, entity))
    if isinstance(action, HelpAction):
        return _pointless_help(battle, entity, action)
    if battle is not None and isinstance(action, DashAction):
        # Nowhere to run to or from: the extra movement has no destination.
        if not conscious_enemies(battle, entity):
            return False
        return (not knows_an_enemy_position(battle, entity) or _dash_in_melee(battle, entity)
                or _dash_without_destination(battle, entity)
                or _dash_after_shooting(battle, entity))
    if battle is not None and isinstance(action, ProneAction):
        return bool(conscious_enemies(battle, entity))
    if battle is not None and isinstance(action, PickpocketAction):
        return bool(conscious_enemies(battle, entity))
    if battle is not None and _non_combat_spell(action):
        return bool(conscious_enemies(battle, entity))
    if _recasts_held_concentration(action, entity):
        return True
    if battle is not None and _pointless_dispel(battle, entity, action):
        return True
    if _spare_the_dying_on_non_dying(action):
        return True
    if battle is not None and isinstance(action, HideAction) and conscious_enemies(battle, entity):
        return _pointless_hide(battle, entity)
    if isinstance(action, WrathOfTheStormAction):
        # On-turn use only picks a damage type; the reaction fires on its own.
        return True
    if isinstance(action, ActionSurgeAction):
        # Spend the turn's action first; surging early can waste the surge.
        return _has_action(battle, entity) or not conscious_enemies(battle, entity)
    if _is_loot(action):
        if in_sight is None:
            in_sight = enemies_present(battle, entity)
        return in_sight
    return False


def filter_actions(battle, entity, actions: Iterable[Any],
                   action_of: Optional[Callable[[Any], Any]] = None) -> List[Any]:
    get = action_of or (lambda a: a)
    items = list(actions)
    in_sight = None
    out = []
    for item in items:
        action = get(item)
        try:
            if _is_loot(action) and in_sight is None:
                in_sight = enemies_present(battle, entity)
            if is_pointless(battle, entity, action, in_sight=in_sight):
                continue
        except Exception:
            pass
        out.append(item)
    try:
        out = _drop_dominated(battle, entity, out, get)
    except Exception:
        pass
    return out


def _drop_dominated(battle, entity, items: List[Any], get) -> List[Any]:
    """Options that only make sense when nothing better is on the list:

    * harmful options aimed only at downed foes while a standing foe can be
      targeted (unless the creature ``finish_downed``); damage past 0 HP only
      adds death save failures;
    * harmful options aimed only at foes held in a Polymorph cast by our own
      side while another standing foe can be targeted: hitting the beast
      form ends the control early and wastes most of the damage;
    * Spare the Dying (cantrip healing) on a creature that a slot healing
      spell on the list would also get back on its feet.
    """
    from natural20.utils.friendly_fire import _creature_targets, is_harmful
    session = getattr(battle, 'session', None)
    opponents = set()
    try:
        opponents = set(battle.opponents_of(entity)) if battle is not None else set()
    except Exception:
        pass

    harmful_on = {}
    for item in items:
        action = get(item)
        targets = [t for t in _creature_targets(action) if t in opponents]
        if targets and is_harmful(action, session):
            harmful_on[id(item)] = targets
    keep_downed = finishes_downed(entity) or not any(
        any(not _downed(t) for t in ts) for ts in harmful_on.values())
    from natural20.utils.polymorph import polymorphed_by_side_of
    held = {id(t) for ts in harmful_on.values() for t in ts
            if polymorphed_by_side_of(t, entity, battle)}
    keep_held = not any(any(id(t) not in held and not _downed(t) for t in ts)
                        for ts in harmful_on.values())

    healed_by_slot = set()
    for item in items:
        level = _healing_level(get(item))
        if level is not None and level >= 1:
            healed_by_slot.update(id(t) for t in _creature_targets(get(item)))

    out = []
    for item in items:
        targets = harmful_on.get(id(item))
        if targets and not keep_downed and all(_downed(t) for t in targets):
            continue
        if targets and not keep_held and all(id(t) in held for t in targets):
            continue
        action = get(item)
        if _healing_level(action) == 0 and healed_by_slot and all(
                id(t) in healed_by_slot for t in _creature_targets(action) or [None]):
            continue
        out.append(item)
    return out
