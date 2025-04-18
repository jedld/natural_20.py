import pdb
from natural20.die_roll import DieRoll
class GenericEventHandler:
    def __init__(self, session, map, properties):
        self.properties = properties
        self.session = session
        self.map = map

    def handle(self, entity, opts=None):
        if opts is None:
            opts = {}

        result = []
        if self.properties.get('if'):
            conditions = self.properties['if']
            if not entity.eval_if(conditions, context={'entity': entity, 'opts': opts}):
                return

        if self.properties.get('message'):
            message = self.session.t(self.properties['message'], options={ "name": entity.label(), "target": opts['target'].label() if opts.get('target') else None })
            self.session.event_manager.received_event({
                'event': 'message',
                'source': entity,
                'message': message
            })

        if self.properties.get('conversation'):
            conversation_properties = self.properties['conversation']
            entity.send_conversation(conversation_properties['message'], conversation_properties.get('distance_ft', 30), conversation_properties.get('targets', []), conversation_properties.get('language', 'common'))

        if self.properties.get('teleport'):
            def handle_teleport(teleport_properties):
                only_alive = teleport_properties.get('only_alive', False)
                entity_uid = teleport_properties['id']

                target_map_name = teleport_properties.get('map', None)
                source_map_name = teleport_properties.get('source_map', None)

                if target_map_name:
                    target_map = self.session.maps[target_map_name]
                else:
                    target_map = self.session.map_for_entity(entity)

                if target_map is None:
                    print("Could not find map")
                    return

                if source_map_name:
                    source_map = self.session.maps[source_map_name]
                    target_entity = source_map.entity_by_uid(entity_uid)
                else:
                    target_entity = self.session.entity_by_uid(entity_uid)
                    source_map = self.session.map_for_entity(target_entity)

                if target_entity is None:
                    print(f"Could not find entity {entity_uid}")
                    return

                if only_alive and target_entity.dead():
                    return

                target_pos = teleport_properties.get('pos', None)
                if target_pos is None:
                    target_pos =  self.map.position_of(entity)
                # check if there is already an entity at pos
                if target_map.entity_at(*target_pos):
                    target_pos = target_map.find_empty_placeable_position(target_entity, *target_pos)

                target_map.add(target_entity, *target_pos)
                source_map.remove(target_entity)

            teleport_properties = self.properties['teleport']
            if isinstance(teleport_properties, list):
                for teleport_property in teleport_properties:
                    handle_teleport(teleport_property)
            else:
                handle_teleport(teleport_properties)

        if self.properties.get('spawn'):
            place_entity_properties = self.properties['spawn']
            if not isinstance(place_entity_properties, list):
                place_entity_properties = [place_entity_properties]

            for place_entity_property in place_entity_properties:
                entity_name = place_entity_property['entity']
                npc_meta = self.map.legend.get(entity_name)
                spawn_entity = self.session.npc(npc_meta['sub_type'], { "name" : npc_meta['name'],
                                                                        "overrides" : npc_meta.get('overrides', {}), "rand_life" : True })

                if place_entity_property.get('pos'):
                    pos = place_entity_property['pos']
                else:
                    pos = self.map.position_of(entity)

                # check if there is already an entity at pos
                if not self.map.placeable(spawn_entity, *pos, squeeze=False):
                    pos = self.map.find_empty_placeable_position(spawn_entity, *pos)

                self.map.add(spawn_entity, *pos, group=npc_meta.get('group', None))

        if self.properties.get('damages'):
            for damage in self.properties['damages']:
                eval_if = damage.get('if', None)
                if eval_if:
                    if not entity.eval_if(eval_if, context=opts):
                        continue

                result.append({
                    'source': entity,
                    'target': opts['target'],
                    'type': 'damage',
                    'attack_name': damage.get('attack_name', 'pit trap'),
                    'damage_type': damage.get('damage_type', 'piercing'),
                    'damage': DieRoll.roll(damage['damage_die'])
                })

        if self.properties.get('update_state'):
            update_state_properties = self.properties['update_state']

            def update_state(entity, update_state_properties):
                target_map_name = update_state_properties.get('map', None)

                if target_map_name:
                    target_map = self.session.maps[target_map_name]
                else:
                    target_map = self.map

                if target_map is None:
                    raise Exception(f"Could not find map {target_map_name}")

                target_request = update_state_properties['target']
                targets = []
                if target_request == 'session':
                    self.session.update_state(update_state_properties['state'])
                elif target_request == 'self':
                    targets.append(entity)
                elif target_request == 'target':
                    targets.append(opts['target'])
                elif isinstance(target_request, list) or isinstance(target_request, tuple):
                    for target in target_request:
                        targets.append(target_map.entity_by_uid(target) or target_map.entity_by_name(target))
                elif target_request.startswith('pos:'):
                    pos = target_request.split(':')
                    targets.append(target_map.entity_at(int(pos[1]), int(pos[2])))
                elif target_request.startswith('objs:'):
                    from natural20.item_library.common import StoneWall, StoneWallDirectional
                    pos = target_request.split(':')
                    targets.extend(target_map.objects_at(int(pos[1]), int(pos[2]), match=[StoneWall, StoneWallDirectional]))
                elif isinstance(target_request, str):
                    targets.append(target_map.entity_by_uid(target_request) or target_map.entity_by_name(target_request))
                # strip None values from targets
                targets = [target for target in targets if target]

                if len(targets) > 0:
                    for target in targets:
                        if target is None:
                            print(f"Could not find target {target_request}")
                            continue
                        states = update_state_properties['state'].split(',')
                        for state in states:
                            if state.strip().lower() == 'delete':
                                for target in targets:
                                    target_map.remove(target)
                            else:
                                target.update_state(state.strip().lower())
                else:
                    print(f"Could not find target {target_request}")
            if isinstance(update_state_properties, list):
                for state_prop in update_state_properties:
                    update_state(entity, state_prop)
            else:
                update_state(entity, update_state_properties)
        return result