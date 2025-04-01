import pdb
import uuid

class ProtectionEffect:
    def __init__(self, entity):
        self.id = uuid.uuid4()
        self.entity = entity
        self.source = None
    
    def __str__(self):
        return "protection"
    
    def __repr__(self):
        return self.__str__()

    def ac_bonus(self, entity, opt=None):
        return 1
    
    def saving_throw_override(self, entity, opt=None):
        return opt['save_roll'] + 1