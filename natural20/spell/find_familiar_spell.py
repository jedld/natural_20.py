from natural20.spell.spell import Spell, consume_resource
from natural20.spell.objects.spiritual_weapon import SpiritualWeapon
from natural20.map import Map
import pdb

class FindFamiliarEffect:
    def __init__(self, source, familiar, battle_map):
        self.source = source
        self.familiar = familiar
        self.battle_map = battle_map

    @property
    def id(self):
        return 'familiar'

    def dismiss(self, entity, effect):
        self.battle_map.remove(self.familiar)

class FindFamiliarSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.familiar = None

    def clone(self):
        spell = super().clone()
        spell.familiar = self.familiar
        return spell

    def build_map(self, orig_action):
        def set_familiar(familiar):
            action = orig_action.clone()
            action.spell_action.familiar = familiar

            def set_target(target):
                action2 = action.clone()
                action2.target = target
                return action2

            return {
                'param': [
                    {
                        'type': 'select_empty_space',
                        'num': 1,
                        'range': 60
                    }
                ],
                'next': set_target
            }

        list_of_familiars = list(self.session.npc_info(familiar=True).keys())
        list_of_familiars.sort()
        return {
            'param': [
                {
                    'type': 'select_choice',
                    'choices': list_of_familiars,
                    'num': 1
                }],
            'next': set_familiar
        }

    def validate(self, battle_map: Map, target=None):
        super().validate(target)
        if target is None:
            target = self.target

        self.errors = []
        if not target:
            self.errors.append("Invalid target")

        if target and (not isinstance(target, tuple) and not isinstance(target, list)) or len(target) != 2:
            self.errors.append("Invalid target type, should be a position")
            return

        if not self.familiar:
            self.errors.append("No familiar selected")
            return

        familiar_npc = self.session.npc(self.familiar)
        # target must be empty space
        if target and not battle_map.placeable(familiar_npc, *target):
            self.errors.append("Target must be empty space")

        if target and not battle_map.distance_to_square(self.source, *target) < 60:
            self.errors.append("Target is out of range")

        if target and not battle_map.can_see_square(self.source, target):
            self.errors.append("Target is not visible")
        
        return len(self.errors) == 0

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item['type'] == 'find_familiar':
            item['source'].remove_effect('find_familiar')

            familiar_npc = session.npc(item['familiar'])
            familiar_npc.owner = item['source']
            familiar_npc.group = item['source'].group

            battle_map = item['map']
            battle_map.place(item['target'], familiar_npc)

            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': FindFamiliarEffect(item['source'], familiar_npc, battle_map)
            })

            session.event_manager.received_event({"event" : 'find_familiar',
                                                  "spell" : item['effect'],
                                                  "source": item['source'],
                                                  "target" : item['target'] })




    def resolve(self, entity, battle, spell_action, battle_map):
        position = spell_action.target
        return [{
            'type': 'find_familiar',
            'map': battle_map,
            'level': spell_action.at_level,
            'target': position,
            'source': spell_action.source,
            'familiar': spell_action.spell_action.familiar,
            'effect': self,
            'spell': self.properties
        }]
