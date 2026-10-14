"""A condition that lasts until the end of the bearer's next turn.

    effect = TimedConditionEffect.apply_to(target, 'stunned', source=aurak, battle=battle)

The status is added to ``target.statuses`` and removed at the end of the
target's next turn. When applied during the target's own turn, that turn's
end doesn't count. Used by NPC ``death_burst`` ``on_fail_condition`` and NPC
area abilities (``natural20/actions/npc_area_action.py``).
"""


class TimedConditionEffect:
    def __init__(self, source, target, condition, skip_current_turn=False):
        self.source = source
        self.target = target
        self.condition = str(condition)
        self.skip_current_turn = bool(skip_current_turn)
        self.id = f"timed_condition:{self.condition}:{id(self)}"

    def __str__(self):
        return self.condition

    @staticmethod
    def timed_condition(entity, opt=None):
        effect = (opt or {}).get('effect')
        return [effect.condition] if effect is not None else []

    @staticmethod
    def end_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return
        if effect.skip_current_turn:
            effect.skip_current_turn = False
            return
        effect.end()

    def end(self):
        target = self.target
        if target is None:
            return
        try:
            target.remove_effect(self)
        except Exception:
            pass
        others = [e for e in (getattr(target, 'effects', None) or {}).get('timed_condition', [])
                  if getattr(e.get('effect') if isinstance(e, dict) else None, 'condition', None) == self.condition]
        statuses = getattr(target, 'statuses', None)
        if not others and isinstance(statuses, list) and self.condition in statuses:
            statuses.remove(self.condition)
        session = getattr(target, 'session', None)
        if session is not None:
            session.event_manager.received_event({
                'event': 'effect_ended', 'source': target, 'target': target,
                'effect_name': self.condition,
            })

    def restore_hooks(self):
        if self.target is not None:
            self.target.register_event_hook('end_of_turn', TimedConditionEffect, effect=self,
                                            source=self.source)

    @classmethod
    def apply_to(cls, target, condition, source=None, battle=None):
        if target is None or target.immune_to_condition(condition):
            return None
        own_turn = False
        if battle is not None:
            try:
                own_turn = battle.current_turn() is target
            except Exception:
                own_turn = False
        effect = cls(source, target, condition, skip_current_turn=own_turn)
        statuses = getattr(target, 'statuses', None)
        if isinstance(statuses, list) and condition not in statuses:
            statuses.append(condition)
        target.register_effect('timed_condition', cls, effect=effect, source=source)
        effect.restore_hooks()
        return effect
