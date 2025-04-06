import pdb
import uuid
from natural20.die_roll import DieRoll


class EngulfEffect:
    from natural20.entity import Entity

    def __init__(self, session, battle, engulfing_entity, entity, save_dc, damage, engulf_map="maps/shambling_mound.yml"):
        self.id = uuid.uuid4()
        self.session = session
        self.battle = battle
        self.entity = entity
        self.engulfing_entity = engulfing_entity
        self.source = None
        self.engulf_map_filename = engulf_map
        self.engulf_map = None
        self.save_dc = save_dc
        self.damage = damage
        self.source_map = None
        self.engulf_map = None

    def __str__(self):
        return "engulf"

    def __repr__(self):
        return self.__str__()

    def engulf(self, entity, opt=None):
        self.source_map = self.session.map_for(entity)
        self.source_map.remove(entity)
        self.engulf_map =self.session.register_map("shambling_mound", self.engulf_map_filename)
        self.engulf_map.add(entity, 1, 1)

    def dismiss(self, entity, opt=None):
        target_map = self.session.map_for(self.engulfing_entity)
        target_pos = target_map.entity_or_object_pos(self.engulfing_entity)
        target_map.add(entity, target_pos[0], target_pos[1])
        self.engulf_map.remove(entity)

    def start_of_turn(self, entity: Entity, opt=None):
        con_save = entity.constitution_saving_throw(self.battle)
        if con_save.result() < self.save_dc:
            self.session.event_manager.received_event({'event': 'generic_failed_save', 'source': self.engulfing_entity, 'target': entity, 'save_type': 'constitution', 'dc': self.save_dc, 'roll': con_save, 'outcome': f"and takes {self.damage} bludgeoning damage."})
            damage = DieRoll.roll_with_lucky(entity, self.damage)
            entity.take_damage(damage, self.battle, damage_type='bludgeoning')
        else:
            self.session.event_manager.received_event({'event': 'generic_success_save', 'source': self.engulfing_entity, 'target': entity, 'save_type': 'constitution', 'dc': self.save_dc, 'roll': con_save, 'outcome': 'and is not affected by the engulf effect.'})

    def restrained_override(self, entity, opt=None):
        return True
