from natural20.action import Action

class GrappleAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    @classmethod
    def can(cls, entity, battle, options=None):
        return (battle is None or entity.total_actions(battle) > 0) and not entity.is_grappling()

    def __str__(self):
        return str(self.action_type).capitalize()

    def validate(self, battle_map, target=None):
        if target is None:
            target = self.target
        if target is None:
            self.errors.append('target is a required option for :attack')
        if (target.size_identifier - self.source.size_identifier) > 1:
            self.errors.append('validation.shove.invalid_target_size')

    def build_map(self):
        def set_target(target):
            self.target = target
            return self
        return {
            'action': self,
            'param': [
                {
                    'type': 'select_target',
                    'range': 5,
                    'target_types': ['enemies', 'allies'],
                    'num': 1
                }
            ],
            'next': set_target
        }

    @classmethod
    def build(cls, session, source):
        action = GrappleAction(session, source, 'grapple')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        target = opts.get('target') or self.target
        battle = opts.get('battle')
        if target is None:
            raise Exception('target is a required option for :attack')
        if (target.size_identifier() - self.source.size_identifier()) > 1:
            return

        strength_roll = self.source.athletics_check(battle)
        athletics_stats = (self.target.athletics_proficient() * self.target.proficiency_bonus()) + self.target.str_mod()
        acrobatics_stats = (self.target.acrobatics_proficient() * self.target.proficiency_bonus()) + self.target.dex_mod()

        grapple_success = False
        if self.target.incapacitated() or not battle.opposing(self.source, target):
            grapple_success = True
        else:
            contested_roll = self.target.athletics_check(battle, description='die_roll.contest') if athletics_stats > acrobatics_stats else self.target.acrobatics_check(battle, description='die_roll.contest')
            grapple_success = strength_roll.result() >= contested_roll.result()

        self.result = [{
            'source': self.source,
            'target': target,
            'type': 'grapple',
            'success': grapple_success,
            'battle': battle,
            'source_roll': strength_roll,
            'target_roll': contested_roll
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'grapple':
            if item['success']:
                if item['target'].immune_to_condition('grappled'):
                    battle.event_manager.received_event({ "event" : 'grapple_immune',
                                                      "target" : item['target'],
                                                      "source" : item['source']})
                    return

                item['target'].do_grappled_by(item['source'])
                battle.event_manager.received_event(  { "event" : 'grapple_success',
                                                      "target" : item['target'],
                                                      "source" : item['source'],
                                                      "source_roll" : item['source_roll'],
                                                      "target_roll" : item['target_roll'] })
            else:
                battle.event_manager.received_event(  { "event" : 'grapple_failure',
                                                        "target" : item['target'],
                                                        "source" : item['source'],
                                                        "source_roll" : item['source_roll'],
                                                        "target_roll" : item['target_roll'] })

            battle.consume(item['source'], 'action')


class DropGrappleAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)

    @classmethod
    def can(cls, entity, battle, options=None):
        return entity.is_grappling()

    def build_map(self):
        return self

    @classmethod
    def build(cls, session, source):
        action = DropGrappleAction(session, source, 'grapple')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        self.result = [{
            'source': self.source,
            'type': 'drop_grapple'
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'drop_grapple':
            item['source'].drop_grapple(item['source'])
            battle.event_manager.received_event({
                "event" : 'drop_grapple',
                "source" : item['source']})
