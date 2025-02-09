import pdb
import uuid

class LifeDrainEffect:
    def __init__(self, battle, entity, hit_point_reduction):
        self.id = uuid.uuid4()
        self.battle = battle
        self.entity = entity
        self.source = None
        self.hit_point_reduction = hit_point_reduction

    def hit_point_max_override(self, entity, opt=None):
        return opt['max_hp'] - self.hit_point_reduction
    
    def long_rest(self, entity, opt=None):
        entity.remove_effect(self)