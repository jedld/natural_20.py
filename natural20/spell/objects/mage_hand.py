import uuid

from natural20.actions.ground_interact_action import GroundInteractAction
from natural20.actions.interact_action import InteractAction
from natural20.actions.move_action import MoveAction
from natural20.entity import Entity


class MageHand(Entity):
    """Spectral hand created by the Mage Hand spell."""

    def __init__(self, session, owner):
        super().__init__(
            name=f"{owner.name}'s Mage Hand",
            description="A spectral, floating hand of force",
            attributes={},
            event_manager=session.event_manager
        )
        self.session = session
        self.owner = owner
        self.group = owner.group
        self.entity_uid = str(uuid.uuid4())
        self.flying = True
        self.targettable = False

        self.properties = {
            'name': f"{owner.name}'s Mage Hand",
            'description': "A spectral, floating hand you control with the Mage Hand spell.",
            'size': 'tiny',
            'speed': 30,
            'speed_fly': 30,
            'actions': []
        }

    def allow_targeting(self):
        return False

    def npc(self):
        return True

    def size(self):
        return 'tiny'

    def hp(self):
        return None

    def max_hp(self):
        return None

    def token(self):
        return ['MH']

    def token_image(self):
        return 'token_mage_hand.png'

    def placeable(self):
        return True

    def passable(self, origin=None):
        return True

    def opaque(self, origin=None):
        return False

    def available_actions(self, session, battle, opportunity_attack=False, map=None, **opts):
        if opportunity_attack:
            return []

        interact_only = opts.get('interact_only', False)

        actions = []

        # Lazy import to avoid circular dependency during module initialization
        from natural20.actions.mage_hand_action import MageHandAction

        if MageHandAction.can(self, battle):
            actions.append(MageHandAction(session, self, 'mage_hand_command'))

        if interact_only:
            return actions

        if MoveAction.can(self, battle):
            actions.append(MoveAction(session, self, 'move'))

        if InteractAction.can(self, battle):
            actions.append(InteractAction(session, self, 'interact'))

        if battle is not None:
            try:
                if GroundInteractAction.items_on_the_ground_count(self, battle) > 0:
                    actions.append(GroundInteractAction(session, self, 'ground_interact'))
            except Exception:
                pass

        return actions

    def label(self):
        return self.properties['name']
