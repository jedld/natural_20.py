"""Bardic Inspiration die carried by a recipient (D&D 5e SRD 2014)."""

from natural20.die_roll import DieRoll

# 10 minutes of in-game time (6 seconds per combat round).
BARDIC_INSPIRATION_DURATION_SECONDS = 10 * 60


class BardicInspirationEffect:
    """One Bardic Inspiration die granted by a bard to another creature."""

    def __init__(self, source, target, die='1d6'):
        self.source = source
        self.target = target
        self.die = die
        self.action = None

    @property
    def id(self):
        return 'bardic_inspiration'

    def __str__(self):
        return 'bardic_inspiration'

    def dismiss(self, entity, effect_entry, opts=None):
        # Recipient-side cleanup only; casted_effects on the bard is managed
        # by Entity.remove_effect when the die is consumed or expires.
        pass


def find_bardic_inspiration_entry(entity):
    """Return the active casted_effects entry for Bardic Inspiration, if any."""
    if entity is None:
        return None
    now = getattr(getattr(entity, 'session', None), 'game_time', None)
    for entry in getattr(entity, 'casted_effects', []):
        effect = entry.get('effect')
        if isinstance(effect, BardicInspirationEffect):
            expiration = entry.get('expiration')
            if expiration is not None and now is not None and expiration <= now:
                continue
            return entry
        if effect == 'bardic_inspiration':
            expiration = entry.get('expiration')
            if expiration is not None and now is not None and expiration <= now:
                continue
            return entry
    return None


def has_bardic_inspiration_die(entity):
    return find_bardic_inspiration_entry(entity) is not None


def bardic_inspiration_die_for(entity):
    entry = find_bardic_inspiration_entry(entity)
    if not entry:
        return None
    effect = entry.get('effect')
    if isinstance(effect, BardicInspirationEffect):
        return effect.die
    return entry.get('die', '1d6')


def remove_bardic_inspiration_die(entity):
    """Consume the inspiration die on ``entity`` (recipient)."""
    entry = find_bardic_inspiration_entry(entity)
    if not entry:
        return False
    effect = entry.get('effect')
    entity.casted_effects = [e for e in entity.casted_effects if e is not entry]
    if effect and hasattr(effect, 'dismiss'):
        effect.dismiss(entity, entry)
    return True


def would_bardic_inspiration_help(base_total, threshold, comparator, die_str):
    """Return True when rolling the max face of ``die_str`` could change the outcome."""
    if threshold is None:
        return False
    detail = DieRoll.parse(die_str)
    if not detail.die_type:
        try:
            max_bonus = int(detail.modifier or 0)
        except (TypeError, ValueError):
            max_bonus = 0
    else:
        sides = int(detail.die_type)
        count = int(detail.die_count or 1)
        max_bonus = count * sides
        if detail.modifier:
            try:
                mod = int(f"{detail.modifier_op or '+'}{detail.modifier}")
            except (TypeError, ValueError):
                mod = 0
            max_bonus += mod

    boosted = base_total + max_bonus
    if comparator in ('ge', None):
        return base_total < threshold <= boosted
    if comparator == 'gt':
        return base_total <= threshold < boosted
    if comparator == 'le':
        return base_total > threshold >= boosted
    if comparator == 'lt':
        return base_total >= threshold > boosted
    return False


def roll_bardic_inspiration_bonus(entity, die_str, battle=None):
    return DieRoll.roll_with_lucky(
        entity,
        die_str,
        description='bardic_inspiration',
        battle=battle,
    )


def prompt_bardic_inspiration_use(entity, battle, context):
    """Ask the entity's controller whether to spend Bardic Inspiration."""
    import inspect

    controller = battle.controller_for(entity) if battle else None
    if controller is not None and hasattr(controller, 'prompt_bardic_inspiration'):
        die_roll = context.get('die_roll')
        metadata = getattr(die_roll, 'metadata', None)
        if metadata is not None and 'bardic_inspiration_choice' in metadata:
            return bool(metadata.pop('bardic_inspiration_choice'))

        choice = controller.prompt_bardic_inspiration(entity, battle, context)
        if inspect.isgenerator(choice):
            from natural20.action import BardicInspirationPrompt
            next(choice)
            raise BardicInspirationPrompt(entity, die_roll, context, choice)
        return bool(choice)
    return would_bardic_inspiration_help(
        context.get('base_total'),
        context.get('threshold'),
        context.get('comparator'),
        context.get('die'),
    )


def apply_bardic_inspiration_to_roll(rollable, entity, threshold, comparator, battle=None):
    """Optionally add a Bardic Inspiration die to ``rollable`` and consume it."""
    from natural20.die_roll import DieRoll, DieRolls

    if rollable is None or entity is None or threshold is None:
        return rollable
    if not has_bardic_inspiration_die(entity):
        return rollable

    if isinstance(rollable, DieRoll) and rollable.metadata.get('bardic_inspiration_applied'):
        return rollable

    die_str = bardic_inspiration_die_for(entity)
    if not die_str:
        return rollable

    if isinstance(rollable, DieRoll):
        base_total = rollable._apply_modifiers(rollable._sum_rolls())
    elif isinstance(rollable, DieRolls):
        base_total = rollable.result()
    else:
        try:
            base_total = int(rollable)
        except (TypeError, ValueError):
            return rollable

    context = {
        'base_total': base_total,
        'threshold': threshold,
        'comparator': comparator,
        'die': die_str,
        'die_roll': rollable,
        'roll_kind': getattr(getattr(rollable, 'metadata', None), 'get', lambda _k, _d=None: None)('roll_kind')
        if isinstance(rollable, DieRoll) else None,
    }
    if isinstance(rollable, DieRoll):
        context['roll_kind'] = rollable.metadata.get('roll_kind')

    if not prompt_bardic_inspiration_use(entity, battle, context):
        return rollable

    inspiration_roll = roll_bardic_inspiration_bonus(entity, die_str, battle=battle)
    bonus = inspiration_roll.result()

    if isinstance(rollable, DieRoll):
        rollable.modifier += bonus
        rollable.metadata['bardic_inspiration_applied'] = True
        rollable.metadata['bardic_inspiration_bonus'] = bonus
        rollable.metadata['bardic_inspiration_roll'] = inspiration_roll
        rollable.metadata['last_result'] = base_total + bonus
    elif isinstance(rollable, DieRolls):
        rollable.rolls.append(inspiration_roll)
    else:
        return rollable

    remove_bardic_inspiration_die(entity)

    event_manager = getattr(entity.session, 'event_manager', None)
    if event_manager:
        event_manager.received_event({
            'event': 'bardic_inspiration_used',
            'source': entity,
            'target': entity,
            'bonus': bonus,
            'die': die_str,
            'roll': inspiration_roll,
        })
    return rollable

