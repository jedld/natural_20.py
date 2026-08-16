from natural20.action import Action

class HelpAction(Action):
    target: any

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.as_bonus_action = False

    @staticmethod
    def can(entity, battle):
        if battle:
            return entity.total_actions(battle) > 0
        return True

    def _help_range(self):
        if self.source and getattr(self.source, 'class_feature', None) and self.source.class_feature('coordinated_strike'):
            return 30
        return 5

    def build_map(self):
        def set_target(target):
            self.target = target
            return self
        return {
            'action': self,
            'param': [
                {
                    'type': 'select_target',
                    'target_types': ['allies', 'enemies'],
                    'exclude_self': True,
                    'range': self._help_range(),
                    'num': 1
                }
            ],
            'next': set_target
        }

    @staticmethod
    def build(session, source):
        action = HelpAction(session, source, 'help')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        if not opts:
            opts = {}

        current_battle = opts.get('battle')
        self.result = [{
            'source': self.source,
            'target': self.target,
            'type': 'help',
            'battle': current_battle,
            'as_bonus_action': bool(self.as_bonus_action),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'help':
            return

        source = item['source']
        target = item['target']
        event_manager = battle.event_manager if battle else session.event_manager

        if target is None:
            return

        try:
            from natural20.spell.sleep_spell import SleepSpell
            if 'sleep' in getattr(target, 'statuses', []):
                if battle:
                    if item.get('as_bonus_action'):
                        battle.consume(source, 'bonus_action')
                    else:
                        battle.consume(source, 'action')
                if SleepSpell.wake_sleeping_target(
                    target, source=source, battle=battle, session=session,
                ):
                    event_manager.received_event({
                        'source': source,
                        'target': target,
                        'event': 'sleep_wake',
                    })
                    return
        except Exception:
            pass

        if battle:
            if item.get('as_bonus_action'):
                battle.consume(source, 'bonus_action')
            else:
                battle.consume(source, 'action')
            event_type = 'help_distract' if battle.opposing(source, target) else 'help'
            if event_type == 'help_distract':
                battle.do_distract(source, target)
                if source.class_feature('coordinated_strike'):
                    source._coordinated_strike_uid = getattr(target, 'entity_uid', None)
            else:
                source.do_help(battle, target)
                if source.class_feature('inspiring_help'):
                    bonus = 2 if source.class_feature('inspiring_help_2') else 1
                    target._inspiring_help_dice = bonus
        else:
            source.do_help(None, target)

        event_manager.received_event({
            'source': source,
            'target': target,
            'event': event_type if battle else 'help'
        })


class HelpBonusAction(HelpAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    @staticmethod
    def can(entity, battle):
        if not battle or entity.total_bonus_actions(battle) <= 0:
            return False
        if not getattr(entity, 'class_feature', None):
            return False
        return bool(entity.class_feature('helpful'))
