from natural20.item_library.object import Object
from natural20.event_manager import EventManager
import pdb

class GenericEventHandler:
    def __init__(self, session, map, properties):
        self.properties = properties
        self.session = session
        self.map = map

    def handle(self, entity, opts=None):
        if self.properties.get('message'):
            self.session.event_manager.received_event({
                'event': 'message',
                'source': entity,
                'message': self.properties['message']
            })

        if self.properties.get('update_state'):
            update_state_properties = self.properties['update_state']
            target_request = update_state_properties['target']
            targets = []
            if target_request == 'self':
                targets.append(entity)
            elif isinstance(target_request, str):
                targets.append(self.map.entity_by_uid(target_request) or self.map.entity_by_name(target_request))
            elif isinstance(target_request, list) or isinstance(target_request, tuple):
                for target in target_request:
                    targets.append(self.map.entity_by_uid(target) or self.map.entity_by_name(target))
            elif target_request.startswith('pos:'):
                pos = target_request.split(':')
                targets.append(self.map.entity_at(int(pos[1]), int(pos[2])))
            if len(targets) > 0:
                for target in targets:
                    states = update_state_properties['state'].split(',')
                    for state in states:
                        target.update_state(state.strip().lower())
            else:
                print(f"Could not find target {target_request}")



class Switch(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.switch_id = self.properties.get('id')
        self.state = self.properties.get('state', 'off')
        self.on_event = self.properties.get('on_event')
        self.off_event = self.properties.get('off_event')
        self.on_message = self.properties.get('on_message')
        self.off_message = self.properties.get('off_message')
        self.events = self.properties.get('events', [])
        for event in self.events:
            handler = GenericEventHandler(session, map, event)
            self.register_event_hook(event['event'], handler, 'handle')

    def interactable(self):
        return not self.is_concealed

    def available_interactions(self, entity, battle=None):
        interactions = super().available_interactions(entity, battle)
        if not self.is_concealed:
            if self.state == 'off':
                interactions['on'] = {}
            else:
                interactions['off'] = {}

        return interactions

    def resolve(self, entity, action, other_params, opts=None):
        result = {}
        if opts is None:
            opts = {}
        if action == 'on':
            self.state = 'on'
            return {
                'action': 'on',
                'source': entity,
                'target': self
            }
        elif action == 'off':
            self.state = 'off'
            return {
                'action': 'off',
                'source': entity,
                'target': self
            }
        return result

    def use(self, entity, result, session=None):
        action = result.get('action')
        if action == 'on':
            self.state = 'on'
            self.resolve_trigger('on')
        elif action == 'off':
            self.state = 'off'
            self.resolve_trigger('off')
        return self