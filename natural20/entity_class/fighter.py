from natural20.actions.second_wind_action import SecondWindAction

class Fighter():
    def __init__(self, name):
        self.name = name
        self.second_wind_count = None
        self.action_surge_count = None

    def initialize_fighter(self):
        self.second_wind_count = 1
        if self.fighter_level >= 2:
            self.action_surge_count = 1
            if self.fighter_level >= 17:
                self.action_surge_count = 2

    def second_wind_die(self):
        return f"1d10+{self.fighter_level}"
    
    def second_wind(self, amt):
        self.second_wind_count -= 1
        self.heal(amt)

    def action_surge(self):
        self.action_surge_count -= 1

    def special_actions_for_fighter(self, session, battle):
        actions = []
        if SecondWindAction.can(self, battle):
            actions.append(SecondWindAction(session, self, 'second_wind'))
        return actions

    def short_rest_for_fighter(self, battle):
        self.second_wind_count = 1
