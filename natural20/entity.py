from natural20.die_roll import DieRoll
class Entity():
    def __init__(self, name, description, attributes = {}):
        self.name = name
        self.description = description
        self.attributes = attributes
        self.statuses = []
        self.ability_scores = {}
        self.entity_event_hooks = {}
        self.effects = {}
        self.casted_effects = []
    
    def __str__(self):
        return f"{self.name}"
    
    def __repr__(self):
        return f"{self.name}"
    
    def name(self):
        return self.name
    
    def hp(self):
        return self.attributes["hp"]
    
    def token_size(self):
        square_size = self.size()
        if square_size == 'tiny':
            return 1
        elif square_size == 'small':
            return 1
        elif square_size == 'medium':
            return 1
        elif square_size == 'large':
            return 2
        elif square_size == 'huge':
            return 3
        else:
            raise ValueError(f"invalid size {square_size}")
        
    def dead(self):
        return 'dead' in self.statuses
    
    def unconscious(self):
        return not self.dead() and 'unconscious' in self.statuses
    
    def conscious(self):
        return not self.dead() and not self.unconscious()
    
    def initiative(self, battle = None):
      roll = DieRoll.roll(f"1d20+#{self.dex_mod()}", description="initiative", entity=self,
                                                        battle=battle)
      value = float(roll.result()) + self.ability_scores.get('dex') / 100.0
      print(f"{self.name} -> initiative roll: {roll} value: {value}")
      # Natural20::EventManager.received_event({ source: self, event: :initiative, roll: roll, value: value })
      return value

    def str_mod(self):
        return self.modifier_table(self.ability_scores.get('str'))

    def con_mod(self):
        return self.modifier_table(self.ability_scores.get('con'))

    def wis_mod(self):
        return self.modifier_table(self.ability_scores.get('wis'))

    def cha_mod(self):
        return self.modifier_table(self.ability_scores.get('cha'))

    def int_mod(self):
        return self.modifier_table(self.ability_scores.get('int'))

    def dex_mod(self):
        return self.modifier_table(self.ability_scores.get('dex'))

    def modifier_table(self, value):
        mod_table = [[1, 1, -5],
                     [2, 3, -4],
                     [4, 5, -3],
                     [6, 7, -2],
                     [8, 9, -1],
                     [10, 11, 0],
                     [12, 13, 1],
                     [14, 15, 2],
                     [16, 17, 3],
                     [18, 19, 4],
                     [20, 21, 5],
                     [22, 23, 6],
                     [24, 25, 7],
                     [26, 27, 8],
                     [28, 29, 9],
                     [30, 30, 10]]

        for low, high, mod in mod_table:
            if low <= value <= high:
                return mod
        return None
    
    def reset_turn(self, battle):
        entity_state = battle.entity_state_for(self)
        entity_state.update({
            'action': 1,
            'bonus_action': 1,
            'reaction': 1,
            'movement': self.speed,
            'free_object_interaction': 1,
            'active_perception': 0,
            'active_perception_disadvantage': 0,
            'two_weapon': None
        })

        if 'dodge' in entity_state['statuses']:
            entity_state['statuses'].remove('dodge')

        if 'disengage' in entity_state['statuses']:
            entity_state['statuses'].remove('disengage')

        battle.dismiss_help_actions_for(self)
        self.resolve_trigger('start_of_turn')
        self._cleanup_effects()
        return entity_state
    
    def resolve_trigger(self, event_type, opts={}):
        if event_type in self.entity_event_hooks:
            active_hook = [effect for effect in self.entity_event_hooks[event_type] if not effect.get('expiration') or effect['expiration'] > self.session.game_time][-1]
            if active_hook:
                active_hook['handler'].send(active_hook['method'], self, {**opts, 'effect': active_hook['effect']})


    def _cleanup_effects(self):
        for key, value in self.effects.items():
            delete_effects = [f for f in value if f.get('expiration') and f['expiration'] <= self.session.game_time]
            for effect in delete_effects:
                self.dismiss_effect(effect)

        self.entity_event_hooks = {k: [f for f in value if not f.get('expiration') or f['expiration'] > self.session.game_time] for k, value in self.entity_event_hooks.items()}

        delete_casted_effects = [f for f in self.casted_effects if f.get('expiration') and f['expiration'] <= self.session.game_time]
        for effect in delete_casted_effects:
            self.dismiss_effect(effect['effect'])

