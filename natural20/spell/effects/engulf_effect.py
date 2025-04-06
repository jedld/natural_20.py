import pdb
import uuid
from natural20.die_roll import DieRoll


class EngulfEffect:
    from natural20.entity import Entity

    def __init__(self, session, battle, engulfing_entity, entity, save_dc, damage, engulf_map="maps/shambling_mound.yml"):
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

    @property
    def id(self):
        return "engulf"

    def __str__(self):
        return "engulf"

    def __repr__(self):
        return self.__str__()

    def engulf(self, entity, opt=None):
        self.source_map = self.session.map_for(entity)
        self.source_map.remove(entity)
        self.engulf_map =self.session.register_map("shambling_mound", self.engulf_map_filename)
        self.battle.register_map(self.engulf_map)
        self.engulf_map.add(entity, 1, 1)
        heart = self.session.npc('heart')
        heart.link_hp(self.engulfing_entity)
        self.engulf_map.add(heart, 1, 0)
        self.entity.do_grappled_by(self.engulfing_entity)

    def dismiss(self, opt=None):
        target_map = self.session.map_for(self.engulfing_entity)
        target_pos = target_map.entity_or_object_pos(self.engulfing_entity)

        if not target_map.placeable(self.entity, target_pos[0], target_pos[1]):
            target_pos = target_map.find_empty_placeable_position(self.entity, target_pos[0], target_pos[1])

        target_map.add(self.entity, target_pos[0], target_pos[1])
        self.engulf_map.remove(self.entity)
        self.entity.escape_grapple_from(self.engulfing_entity)
        self.battle.unregister_map(self.engulf_map)

    def start_of_turn(self, entity: Entity, opt=None):
        con_save = entity.saving_throw('constitution', self.battle)
        if con_save.result() < self.save_dc:
            self.session.event_manager.received_event({'event': 'generic_failed_save', 'effect_description': 'engulf', 'source': self.entity, 'target':  self.engulfing_entity, 'save_type': 'constitution', 'dc': self.save_dc, 'roll': con_save, 'outcome': f"and takes {self.damage} bludgeoning damage."})
            damage = DieRoll.roll_with_lucky(entity, self.damage)
            entity.take_damage(damage.result(), self.battle, damage_type='bludgeoning')
        else:
            self.session.event_manager.received_event({'event': 'generic_success_save', 'effect_description': 'engulf', 'source': self.entity, 'target':  self.engulfing_entity, 'save_type': 'constitution', 'dc': self.save_dc, 'roll': con_save, 'outcome': 'and is not affected by the engulf effect.'})

    def escape_grapple_from(self, entity, opt=None):
        self.dismiss()

    def restrained_override(self, entity, opt=None):
        return True
