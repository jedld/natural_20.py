import random
class GenericController:
    def __init__(self):
        self.state = {}

    def roll_for(self, entity, stat, advantage=False, disadvantage=False):
        return None
    
    def move_for(self, entity, battle, available_moves = []):
        # choose available moves at random and return it
        if len(available_moves) > 0:
            return random.choice(available_moves)
        
        return None
        