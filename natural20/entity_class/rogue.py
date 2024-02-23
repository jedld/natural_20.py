# typed: false
class Rogue:
    def __init__(self):
        self.rogue_level = None

    def initialize_rogue(self):
        pass

    def sneak_attack_level(self):
        levels = [
            "1d6", "1d6",
            "2d6", "2d6",
            "3d6", "3d6",
            "4d6", "4d6",
            "5d6", "5d6",
            "6d6", "6d6",
            "7d6", "7d6",
            "8d6", "8d6",
            "9d6", "9d6",
            "10d6", "10d6",
        ]
        return levels[self.rogue_level]

    def special_actions_for_rogue(self, session, battle):
        return []
