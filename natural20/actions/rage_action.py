from natural20.action import Action


class RageAction(Action):
    """Bonus-action: enter Rage (D&D 5e SRD, Barbarian L1).

    While raging:
      * Resistance to bludgeoning, piercing, slashing damage.
      * Bonus damage on STR-based melee weapon attacks (rage damage).
      * Advantage on STR ability checks/saves (flag, callers may consult).
      * Lasts 10 rounds (1 minute).
    """

    @staticmethod
    def can(entity, battle):
        if not getattr(entity, 'has_rage', None):
            return False
        if not getattr(entity, 'barbarian_level', 0):
            return False
        if entity.is_raging():
            return False
        if not entity.has_rage(1):
            return False
        if battle is None:
            return True
        return entity.total_bonus_actions(battle) > 0

    def label(self):
        uses = getattr(self.source, 'rage_count', 0)
        return f"Rage ({uses})"

    def __str__(self):
        return "Rage"

    __repr__ = __str__

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        return RageAction(session, source, 'rage').build_map()

    def resolve(self, _session, _map, opts=None):
        battle = (opts or {}).get('battle')
        self.result = [{
            'source': self.source,
            'type': 'rage_start',
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if session is None and battle is not None:
            session = battle.session
        if item['type'] == 'rage_start':
            source = item['source']
            source.begin_rage()
            if session is not None:
                session.event_manager.received_event({
                    'source': source,
                    'event': 'rage_start',
                    'rounds': source.rage_rounds_remaining,
                })
            if battle is not None:
                battle.consume(source, 'bonus_action')

    @staticmethod
    def describe(event):
        return f"{event['source'].name} enters a rage"


class RecklessAttackAction(Action):
    """Free toggle: declare Reckless Attack for the current turn (Barbarian L2).

    Effects (handled in ``natural20.weapons``):
      * Advantage on STR-based melee weapon attack rolls this turn.
      * Attacks against the barbarian have advantage until the start of
        the barbarian's next turn.
    """

    @staticmethod
    def can(entity, battle):
        if not entity.class_feature('reckless_attack'):
            return False
        if entity.is_reckless():
            return False
        # Reckless Attack costs nothing - it is a choice attached to the
        # Attack action.  Only require the barbarian to have an action
        # available so the menu does not surface it on a fully spent turn.
        if battle is None:
            return True
        state = battle.entity_state_for(entity)
        if not state:
            return False
        return state.get('action', 0) > 0

    def label(self):
        return 'Reckless Attack'

    def __str__(self):
        return "RecklessAttack"

    __repr__ = __str__

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        return RecklessAttackAction(session, source, 'reckless_attack').build_map()

    def resolve(self, _session, _map, opts=None):
        battle = (opts or {}).get('battle')
        self.result = [{
            'source': self.source,
            'type': 'reckless_attack',
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if session is None and battle is not None:
            session = battle.session
        if item['type'] == 'reckless_attack':
            source = item['source']
            source.use_reckless_attack()
            if session is not None:
                session.event_manager.received_event({
                    'source': source,
                    'event': 'reckless_attack',
                })

    @staticmethod
    def describe(event):
        return f"{event['source'].name} attacks recklessly"


class EndRageAction(Action):
    """Bonus action: drop your rage early (engine convenience)."""

    @staticmethod
    def can(entity, battle):
        if not getattr(entity, 'is_raging', None):
            return False
        if not entity.is_raging():
            return False
        if battle is None:
            return True
        return entity.total_bonus_actions(battle) > 0

    def label(self):
        return 'End Rage'

    def __str__(self):
        return 'EndRage'

    __repr__ = __str__

    def build_map(self):
        return self

    def resolve(self, _session, _map, opts=None):
        battle = (opts or {}).get('battle')
        self.result = [{
            'source': self.source,
            'type': 'rage_end',
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if session is None and battle is not None:
            session = battle.session
        if item['type'] == 'rage_end':
            item['source'].end_rage(reason='manual')
            if battle is not None:
                battle.consume(item['source'], 'bonus_action')
