"""Darkness spell — creates a 15-foot sphere of magical darkness."""
from natural20.spell.spell import Spell
from natural20.spell.objects.darkness import Darkness
from natural20.map import Map


class DarknessEffect:
    """Concentration effect: removes the placed Darkness object on dismiss."""

    def __init__(self, source, darkness, battle_map):
        self.source = source
        self.darkness = darkness
        self.battle_map = battle_map

    @property
    def id(self):
        return 'darkness'

    def __str__(self):
        return 'Darkness'

    def dismiss(self, entity, effect, opts=None):
        if self.darkness in self.battle_map.entities:
            self.battle_map.remove(self.darkness)


class DarknessSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)

    # ---- targeting -----------------------------------------------------
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        return {
            'param': [
                {
                    'type': 'select_empty_space',
                    'num': 1,
                    'range': self.properties.get('range', 60)
                }
            ],
            'next': set_target
        }

    def validate(self, battle_map: Map, target=None):
        super().validate(target)
        if target is None:
            target = self.target

        self.errors = []
        if target is None:
            self.errors.append("Invalid target")
            return False

        if not (isinstance(target, (tuple, list)) and len(target) == 2):
            self.errors.append("Invalid target type, should be a position")
            return False

        # Allow casting onto an empty square within range.
        if battle_map and battle_map.entity_at(*target) is not None:
            self.errors.append("Target must be empty space")

        if battle_map and battle_map.distance_to_square(self.source, *target) > self.properties.get('range', 60):
            self.errors.append("Target is out of range")

        return len(self.errors) == 0

    # ---- resolution ----------------------------------------------------
    def resolve(self, entity, battle, spell_action, battle_map):
        return [{
            'type': 'darkness',
            'map': battle_map,
            'level': spell_action.at_level,
            'target': spell_action.target,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'darkness':
            return

        if battle and session is None:
            session = battle.session

        source = item['source']
        battle_map = item['map']
        position = item['target']

        # End any previous Darkness this caster is concentrating on so the
        # caster can never have two concurrent magical darkness instances.
        source.remove_effect('darkness')

        radius_feet = item['spell'].get('radius', 15)
        darkness = Darkness(session, source, radius_feet=radius_feet)
        battle_map.place(position, darkness)

        effect = DarknessEffect(source, darkness, battle_map)

        # Concentration tracking + dismissal hook on the caster.
        source.add_casted_effect({
            'target': position,
            'effect': effect,
            'expiration': session.game_time + 10 * 60,  # 10 minutes
        })
        source.register_effect(
            'darkness', DarknessSpell, effect=effect, source=source,
            duration=10 * 60,
        )
        source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'darkness',
            'spell': effect,
            'source': source,
            'target': position,
        })
