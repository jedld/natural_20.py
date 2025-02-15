from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.npc import Npc
from natural20.player_character import PlayerCharacter

class SpareTheDyingSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        current_range = 15
        if self.source.level() >= 5:
            current_range = 30
        if self.source.level() >= 11:
            current_range = 45
        if self.source.level() >= 17:
            current_range = 60
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': current_range,
                    'target_types': ['allies', 'self', 'enemies']
                }
            ],
            'next': set_target
        }

    def compute_hit_probability(self, battle, opts=None):
        return 1.0

    def avg_damage(self, battle, opts=None):
        return 0

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        return [{
            "source": entity,
            "target": target,
            "type": "spare_the_dying",
            "spell": self.properties
        }]

    def validate(self, battle_map, target=None):
        if target is None:
            self.errors.append("target is a required option")

        if target is not None and target.stable():
            self.errors.append("target is already stable")

        if target is not None and target.dead():
            self.errors.append("target is dead")

        if target is not None and not target.unconscious():
            self.errors.append("target is not unconscious")

        if target.hp() > 0:
            self.errors.append("target is not unconscious")

        if not isinstance(target, Npc) or isinstance(target, PlayerCharacter):
            self.errors.append("target must be an entity")


    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'spare_the_dying':
           item['target'].make_stable()
           battle.event_manager.received_event({ "event" : 'first_aid',
                                                  "target": item['target'],
                                                  "source": item['source'],
                                                  "success": True,
                                                  "roll" : item['roll'] })
           battle.consume(item['source'], 'action')