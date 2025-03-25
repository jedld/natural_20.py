from natural20.concern.generic_event_handler import GenericEventHandler

class EventLoader:
    def register_event_handlers(self, session, map, properties):
        if 'ability_checks' in properties:
            for ability, check_props in properties['ability_checks'].items():
                for outcome in ('success', 'failure'):
                    outcome_props = check_props.get(outcome)
                    if isinstance(outcome_props, dict):
                        events = outcome_props.get('events', [])
                        for event in events:
                            handler = GenericEventHandler(session, map, event)
                            self.register_event_hook(f"{ability}_check_{outcome}", handler, 'handle')

        events = properties.get('events', [])
        for event in events:
            handler = GenericEventHandler(session, map, event)
            if isinstance(event['event'], list):
                for e in event['event']:
                    self.register_event_hook(e, handler, 'handle')
            else:
                self.register_event_hook(event['event'], handler, 'handle')
        return events
