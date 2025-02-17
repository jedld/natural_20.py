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

        if self.properties.get('spawn'):
            place_entity_properties = self.properties['spawn']
            entity_name = place_entity_properties['entity']
            npc_meta = self.map.legend.get(entity_name)
            spawn_entity = self.session.npc(npc_meta['sub_type'], { "name" : npc_meta['name'], "overrides" : npc_meta.get('overrides', {}), "rand_life" : True })

            if place_entity_properties.get('pos'):
                pos = place_entity_properties['pos']
            else:
                pos = self.map.position_of(entity)

            self.map.add(spawn_entity, *pos, group=npc_meta.get('group', None))

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