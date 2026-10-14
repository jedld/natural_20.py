from natural20.weapons import target_advantage_condition
from natural20.utils.attack_util import after_attack_roll_hook
from natural20.utils.ac_utils import effective_ac
from natural20.die_roll import DieRoll


def _cached_roll(action, attack_index):
    if action is None:
        return None
    if attack_index is None:
        return getattr(action, 'attack_roll', None)
    return (getattr(action, 'attack_rolls_by_index', None) or {}).get(attack_index)


def _store_roll(action, attack_index, attack_roll):
    if action is None:
        return
    action.attack_roll = attack_roll
    if attack_index is not None:
        rolls = getattr(action, 'attack_rolls_by_index', None) or {}
        rolls[attack_index] = attack_roll
        action.attack_rolls_by_index = rolls


def _consume_one_shot_effects(events):
    """Apply ``dismiss_effect`` hook results now (e.g. Guiding Bolt's
    advantage), so later attacks of the same spell don't benefit too. The
    items stay in the result; dismissing again at commit is a no-op."""
    for event in events:
        if event.get('type') == 'dismiss_effect' and not event.get('_consumed_at_resolve'):
            try:
                event['source'].dismiss_effect(event['effect'])
            except Exception:
                continue
            event['_consumed_at_resolve'] = True


def _mirror_image(action, entity, target, attack_roll, hit, battle):
    from natural20.spell.mirror_image_spell import MirrorImageSpell
    checks = getattr(action, 'mirror_image_checks', None) if action is not None else None
    if checks is None:
        checks = []
    for roll, checked_target, outcome in checks:
        if roll is attack_roll and checked_target is target:
            return outcome
    outcome = MirrorImageSpell.check_attack(entity, target, attack_roll, hit, battle)
    if action is not None:
        checks.append((attack_roll, target, outcome))
        action.mirror_image_checks = checks
    return outcome


def mirror_image_outcome_for(action, attack_roll, target):
    """The Mirror Image outcome recorded for this spell attack, if any."""
    for roll, checked_target, outcome in (getattr(action, 'mirror_image_checks', None) or []):
        if roll is attack_roll and checked_target is target:
            return outcome
    return None


def evaluate_spell_attack(session, entity, target, spell_properties, battle=None, opts=None):
    """Roll one spell attack against *target*.

    Spells that make several attacks in one cast (Scorching Ray rays,
    Eldritch Blast beams) pass ``opts['attack_index']`` so each attack gets
    its own roll (cached per index on the action for re-resolves) and a
    one-shot effect such as Guiding Bolt's advantage only helps the first.
    """
    if opts is None:
        opts = {}
    action = opts.get('action', None)
    attack_index = opts.get('attack_index')

    # DnD 5e advantage/disadvantage checks
    advantage_mod, adv_info = target_advantage_condition(session, entity, target, spell_properties, battle=battle, overrides=opts)

    attack_roll = _cached_roll(action, attack_index)
    fresh_roll = attack_roll is None

    if attack_roll is None:
        if spell_properties.get('type') == 'melee_attack':
            if entity.familiar():
                attack_roll = entity.owner.melee_spell_attack(battle, spell_properties, advantage=advantage_mod > 0,
                                                disadvantage=advantage_mod < 0)
            else:
                attack_roll = entity.melee_spell_attack(battle, spell_properties, advantage=advantage_mod > 0,
                                                disadvantage=advantage_mod < 0)
        else:
            attack_roll = entity.ranged_spell_attack(battle, spell_properties, advantage=advantage_mod > 0,
                                                                                    disadvantage=advantage_mod < 0)

        if entity.has_effect('bless'):
            bless_roll = DieRoll.roll("1d4", description='dice_roll.bless', entity=entity, battle=battle)
            attack_roll += bless_roll
        from natural20.effects.consumable_buff_effect import attack_roll_dice
        for extra_die in attack_roll_dice(entity, battle):
            attack_roll += extra_die
        if entity.has_effect('bane'):
            bane_roll = DieRoll.roll("1d4", description='dice_roll.bane', entity=entity, battle=battle)
            attack_roll += DieRoll.roll("-" + str(bane_roll.result()), battle=battle, entity=entity)
        from natural20.utils.attack_penalties import apply_targeted_penalties
        attack_roll = apply_targeted_penalties(attack_roll, entity, target, battle)

        _store_roll(action, attack_index, attack_roll)

    target_ac, _cover_ac = effective_ac(battle, entity, target, spell_attack=True)

    if fresh_roll and battle is not None and target is not None and hasattr(target, 'entity_uid'):
        from natural20.utils.luck_points import luck_against_attack, luck_on_own_roll
        attack_roll = luck_on_own_roll(entity, attack_roll, target_ac, battle=battle, target=target)
        attack_roll = luck_against_attack(target, entity, attack_roll, target_ac, battle=battle)
        _store_roll(action, attack_index, attack_roll)

    entity.resolve_trigger('attack_resolved', { "target" : target})

    force_miss, events = after_attack_roll_hook(battle, target,
                                        entity, attack_roll, target_ac, { "spell" : spell_properties,
                                                                          "hit_reaction_action": action})
    if attack_index is not None:
        _consume_one_shot_effects(events)
    if not force_miss:
        cover_ac_adjustments = 0
        hit = True if attack_roll.nat_20() else False if attack_roll.nat_1() else attack_roll.result() >= target_ac
    else:
        cover_ac_adjustments = None
        hit = False

    if target is not None and hasattr(target, 'entity_uid'):
        if _mirror_image(action, entity, target, attack_roll, hit, battle) is not None:
            hit = False

    return [hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events]
