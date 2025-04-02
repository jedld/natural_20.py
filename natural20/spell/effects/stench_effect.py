import pdb
import uuid

class StenchEffect:
    def __init__(self, battle, entity):
        self.id = uuid.uuid4()
        self.battle = battle
        self.entity = entity
        self.source = None

    def __str__(self):
        return "stench"

    def __repr__(self):
        return self.__str__()

    def poisoned(self, entity, opt=None):
        return True
    
    def remove_effect(self, entity, opt=None):
        entity.remove_effect(self)

    def start_of_turn(self, entity, opt=None):
        battle_map = self.battle.map_for(entity)
        if not battle_map:
            return
            
        for nearby_entity in battle_map.entities_in_range(entity, 5):
            attributes = nearby_entity.properties.get('attributes', [])
            
            # Skip if not a stench entity or is the same entity or entity is immune
            if ('stench' not in attributes or 
                nearby_entity == entity or 
                'poisoned' in entity.condition_immunities):
                continue
                
            # Perform constitution save against stench
            dc = nearby_entity.properties.get('stench_dc', 10)
            result = entity.save_throw('constitution', battle=self.battle)
            stench_description = f"stench from {nearby_entity.label()}"
            
            # Create event data common to both success and failure
            event_data = {
                "source": entity,
                "effect_description": stench_description,
                "save_type": 'constitution',
                "dc": dc,
                "roll": result
            }
            
            if result < dc:
                # Failed save - apply poisoned effect
                entity.register_event_hook('start_of_turn', self, method_name='remove_effect', 
                                          effect=self, source=nearby_entity, duration=None)
                entity.register_effect('poisoned', self, method_name='poisoned', 
                                      effect=self, source=nearby_entity, duration=None)
                
                # Add failure-specific event data
                event_data.update({
                    "event": 'generic_failed_save',
                    "outcome": f"{entity.label()} is now poisoned by the stench of {nearby_entity.label()}"
                })
            else:
                # Successful save
                event_data["event"] = 'generic_success_save'
                
            self.battle.event_manager.received_event(event_data)