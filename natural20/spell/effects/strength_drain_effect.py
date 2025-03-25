import pdb
import uuid

class StrengthDrainEffect:
    def __init__(self, battle, entity, strength_reduction):
        self.id = uuid.uuid4()
        self.battle = battle
        self.entity = entity
        self.source = None
        self.strength_reduction = strength_reduction

    def __str__(self):
        return "strength_drain"

    def __repr__(self):
        return self.__str__()

    def strength_override(self, entity, opt=None):
        return opt['strength'] - self.strength_reduction

    def long_rest(self, entity, opt=None):
        entity.remove_effect(self)

    def short_rest(self, entity, opt=None):
        entity.remove_effect(self)