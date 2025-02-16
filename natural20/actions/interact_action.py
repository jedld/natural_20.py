from natural20.action import Action
import pdb

class InteractAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        if opts:
            self.target = opts.get('target')
            self.object_action = opts.get('object_action')
            self.other_params = opts.get('other_params')
        else:
            self.target = None
            self.object_action = None
            self.other_params = None

    def __str__(self):
        return f"Interact({self.target},{self.object_action})"
    
    def __repr__(self):
        return self.__str__()
    
    def label(self):
        if self.disabled:
            return f"{self.source} cannot {self.action_type} with [{self.target}] because of [{self.disabled_reason}]"
        else:
            return f"{self.object_action} {self.target}"

    def button_label(self):
        if self.target and self.object_action:
            button_info = self.target.buttons.get(self.object_action)
            if button_info:
                return button_info.get('label', self.object_action)
        return None

    def button_image(self):
        if self.target and self.object_action:
            button_info = self.target.buttons.get(self.object_action)
            if button_info:
                return button_info.get('image')
        return None

    @staticmethod
    def can(entity, battle):
        return battle is None or not battle.ongoing or entity.total_actions(battle) > 0 or entity.free_object_interaction(battle)

    @staticmethod
    def build(session, source):
        action = InteractAction(session, source=source, action_type='interact')
        return action.build_map()
    
    def clone(self):
        interact_action = InteractAction(self.session, self.source, self.action_type, self.opts)
        interact_action.target = self.target
        interact_action.object_action = self.object_action
        interact_action.other_params = self.other_params.copy() if self.other_params else None
        return interact_action

    def build_map(self):
        return {
            'action': self,
            'param': [
                {
                    'type': 'select_object'
                }
            ],
            'next': lambda object: self.build_next(object)
        }

    def build_next(self, object):
        action = self.clone()
        action.target = object
        return {
            'param': [
                {
                    'type': 'interact',
                    'target': object
                }
            ],
            'next': lambda interaction: action.build_custom_action(interaction, object)
        }

    def build_custom_action(self, interaction, object):
        action = self.clone()
        action.object_action = interaction
        custom_action = object.build_map(interaction, action) if object else None

        if custom_action is None:
            return action
        else:
            return custom_action

    def resolve(self, session, map=None, opts=None):
        battle = opts.get('battle') if opts else None

        result = self.target.resolve(self.source, self.object_action, self.other_params, opts)

        if result is None:
            return []

        result_payload = {
            'source': self.source,
            'target': self.target,
            'object_action': self.object_action,
            'map': map,
            'battle': battle,
            'type': 'interact'
        }
        result_payload.update(result)
        self.result = [result_payload]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        entity = item['source']
        item_type = item['type']
        if session is None:
            session = battle.session

        if item_type == 'interact':
            item['target'].use(entity, item, session)
            if battle:
                if item.get('cost') == 'action':
                    battle.consume(entity, 'action', 1)
                else:
                    battle.consume(entity, 'free_object_interaction', 1) or battle.consume(entity, 'action', 1)

                session.event_manager.received_event({
                        "event": 'interact', 
                        "source": entity, 
                        "target": item['target'],
                        "object_action": item['object_action']})
            else:
                if session:
                    session.event_manager.received_event({
                        "event": 'interact', 
                        "source": entity, 
                        "target": item['target'],
                        "object_action": item['object_action']})
                    
    def to_h(self):
        return {
            "action_type": self.action_type,
            "target": self.target.entity_uid if self.target else None,
            "object_action": self.object_action
        }