"""Tabaxi racial trait - Feline Agility.

When a Tabaxi moves on its turn in combat, it can double its speed
until the end of that turn. Once used, the trait can't be used again
until the Tabaxi moves 0 feet on one of its turns (D&D 5e Volo's /
Mordenkainen's: Monsters of the Multiverse).

This is a "no action" feature - the player declares it once on their
turn and it grants extra movement immediately. We model it as an
Action with no resource cost so it appears in the action menu.
"""

from natural20.action import Action


class FelineAgilityAction(Action):
    def label(self):
        return 'Feline Agility (double speed)'

    def __repr__(self):
        return 'FelineAgility()'

    @staticmethod
    def can(entity, battle, options=None):
        if not battle:
            return False
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('feline_agility'):
            return False
        if getattr(entity, 'feline_agility_used', False):
            return False
        state = battle.entity_state_for(entity)
        if not state:
            return False
        return True

    def build_map(self):
        return self

    def resolve(self, _session, _map, opts=None):
        opts = opts or {}
        self.result = [{
            'type': 'feline_agility',
            'source': self.source,
            'battle': opts.get('battle'),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'feline_agility':
            return
        if session is None:
            session = battle.session if battle else None
        source = item['source']
        # Mark the trait as expended; will reset when source moves 0 ft
        # on a future turn.
        source.feline_agility_used = True
        if battle:
            state = battle.entity_state_for(source)
            if state is not None:
                # Add the source's base speed to remaining movement.
                state['movement'] = state.get('movement', 0) + source.speed()
        if session:
            session.event_manager.received_event({
                'source': source,
                'event': 'feline_agility',
            })
