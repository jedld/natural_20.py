from natural20.actions.attack_action import AttackAction


class DisarmingAttackAction(AttackAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.maneuver = 'disarming_attack'

    def label(self):
        return f"Disarming Attack ({self.source.superiority_die()})"

    def __repr__(self):
        return "DisarmingAttack"

    def clone(self):
        action = DisarmingAttackAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        action.using = self.using
        action.npc_action = self.npc_action
        action.as_reaction = self.as_reaction
        action.thrown = self.thrown
        action.advantage_mod = self.advantage_mod
        action.attack_roll = self.attack_roll
        return action

    @staticmethod
    def can(entity, battle, options=None):
        if not battle or not AttackAction.can(entity, battle, options):
            return False
        return (
            getattr(entity, 'has_maneuver', lambda _m: False)('disarming_attack')
            and entity.has_resource('superiority_dice')
        )

    @staticmethod
    def build(session, source):
        action = DisarmingAttackAction(session, source, 'disarming_attack')
        return action.build_map()
