"""Action: break a creature (yourself or one within reach) out of a magical restraint.

Effects opt in by registering an ``escapable_restraint`` effect on the
restrained creature whose effect object exposes:

* ``escape_dc`` — DC of the check,
* ``escape_skill`` — skill used (default ``athletics``; the check is a
  Strength (Athletics) check for Ensnaring Strike),
* ``break_free(creature, by)`` — optional; ends the effect (defaults to
  ``creature.remove_effect(effect)``).
"""
from natural20.action import Action

EFFECT_KEY = 'escapable_restraint'


def restraints_on(creature):
    out = []
    for entry in (getattr(creature, 'effects', None) or {}).get(EFFECT_KEY, []) or []:
        effect = entry.get('effect')
        expiration = entry.get('expiration')
        session = getattr(creature, 'session', None)
        if expiration is not None and session is not None and expiration <= session.game_time:
            continue
        if effect is not None and getattr(effect, 'escape_dc', None):
            out.append(effect)
    return out


class BreakFreeAction(Action):
    REACH_FT = 5

    def __init__(self, session, source, action_type='break_free', opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.restraint = None

    def clone(self):
        action = BreakFreeAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        action.restraint = self.restraint
        return action

    def label(self):
        name = getattr(self.restraint, 'escape_label', None) or 'restraint'
        if self.target is not None and self.target is not self.source:
            return f"Free {getattr(self.target, 'name', 'ally')} ({name})"
        return f"Break Free ({name})"

    def name(self):
        return self.label()

    def button_image(self):
        return 'break_free'

    @staticmethod
    def candidates(entity, battle):
        """``[(creature, restraint), ...]``: itself plus allies within reach."""
        creatures = [entity]
        battle_map = battle.map_for(entity) if battle is not None else None
        if battle is not None:
            creatures += [e for e in battle.allies_of(entity) if e is not entity]
        out = []
        for creature in creatures:
            restraints = restraints_on(creature)
            if not restraints:
                continue
            if creature is not entity:
                if battle_map is None or battle.map_for(creature) is not battle_map:
                    continue
                if battle_map.distance(entity, creature) * battle_map.feet_per_grid > BreakFreeAction.REACH_FT:
                    continue
            for restraint in restraints:
                out.append((creature, restraint))
        return out

    @staticmethod
    def can(entity, battle, options=None):
        if battle is not None and entity.total_actions(battle) <= 0:
            return False
        if hasattr(entity, 'conscious') and not entity.conscious():
            return False
        return bool(BreakFreeAction.candidates(entity, battle))

    @staticmethod
    def options_for(session, entity, battle):
        if not BreakFreeAction.can(entity, battle):
            return []
        options = []
        for creature, restraint in BreakFreeAction.candidates(entity, battle):
            action = BreakFreeAction(session, entity)
            action.target = creature
            action.restraint = restraint
            options.append(action)
        return options

    def available(self, battle):
        return BreakFreeAction.can(self.source, battle)

    @staticmethod
    def build(session, source):
        return BreakFreeAction(session, source).build_map()

    def build_map(self):
        def set_target(target):
            action = self.clone()
            action.target = target[0] if isinstance(target, (list, tuple)) else target
            return action

        return {
            'action': self,
            'param': [{'type': 'select_target', 'num': 1, 'range': self.REACH_FT,
                       'target_types': ['self', 'allies']}],
            'next': set_target,
        }

    def ai_value(self, battle):
        restraint = self.restraint or next(iter(restraints_on(self.target or self.source)), None)
        if restraint is None:
            return 0
        mod = 0
        skill = getattr(restraint, 'escape_skill', 'athletics') or 'athletics'
        try:
            mod = int(getattr(self.source, f"{skill}_mod")())
        except Exception:
            pass
        chance = max(0.05, min(0.95, (21 - (int(restraint.escape_dc) - mod)) / 20.0))
        return 2.0 * chance

    def resolve(self, session, map=None, opts=None):
        battle = (opts or {}).get('battle')
        target = self.target or self.source
        restraint = self.restraint or next(iter(restraints_on(target)), None)
        self.result = []
        if restraint is None:
            return self
        skill = getattr(restraint, 'escape_skill', 'athletics') or 'athletics'
        check = getattr(self.source, f"{skill}_check", None)
        if callable(check):
            roll = check(battle, description=f'dice_roll.{skill}')
        else:
            roll = self.source.strength_check(battle=battle, description='dice_roll.strength')
        dc = int(restraint.escape_dc)
        self.result.append({
            'type': 'break_free',
            'source': self.source,
            'target': target,
            'restraint': restraint,
            'roll': roll,
            'dc': dc,
            'skill': skill,
            'success': roll.result() >= dc,
        })
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'break_free':
            return None
        session = session or (battle.session if battle is not None else item['source'].session)
        target, restraint = item['target'], item['restraint']
        if battle is not None:
            battle.consume(item['source'], 'action')
        if item['success']:
            breaker = getattr(restraint, 'break_free', None)
            if callable(breaker):
                breaker(target, item['source'])
            else:
                target.remove_effect(restraint)
        session.event_manager.received_event({
            'event': 'break_free',
            'source': item['source'],
            'target': target,
            'roll': item['roll'],
            'dc': item['dc'],
            'success': item['success'],
            'restraint': getattr(restraint, 'escape_label', None) or str(restraint),
        })
        return None


from natural20.utils.class_feature_registry import register_class_feature  # noqa: E402

register_class_feature(
    feature_id='break_free',
    action_class=BreakFreeAction,
    provides=lambda entity: True,
    builder=lambda session, entity, feature_id, battle=None: BreakFreeAction.options_for(
        session, entity, battle),
)
