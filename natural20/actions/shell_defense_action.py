"""Tortle racial trait - Shell Defense.

The tortle can withdraw into their shell as an action. While in the shell:
- +4 bonus to AC
- Advantage on Strength and Constitution saving throws
- Disadvantage on Dexterity saving throws
- Prone, speed 0, can't increase speed
- No reactions
- Only action possible is bonus action to emerge

Once used, the trait can't be used again until the tortle emerges.
(Monts of the Multiverse SRD - Tortle racial trait)
"""

from natural20.action import Action


class ShellDefenseAction(Action):
    def label(self):
        return 'Shell Defense (+4 AC, prone)'

    def __repr__(self):
        return 'ShellDefense()'

    @staticmethod
    def can(entity, battle, options=None):
        if not battle:
            return False
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('shell_defense'):
            return False
        # Can't use if already in shell
        if getattr(entity, '_in_shell', False):
            return False
        return True

    def build_map(self):
        return self

    def resolve(self, session, map_, opts=None):
        opts = opts or {}
        self.result = [{
            'type': 'shell_defense',
            'source': self.source,
            'battle': opts.get('battle'),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'shell_defense':
            return
        if session is None:
            session = battle.session if battle else None
        source = item['source']
        # Enter shell state
        source._in_shell = True
        # Mark prone
        source._prone = True
        if battle:
            state = battle.entity_state_for(source)
            if state is not None:
                # Set speed to 0 while in shell
                state['movement'] = 0
            battle.event_manager.received_event({
                'source': source,
                'event': 'shell_defense_enter',
            })
        if session:
            session.event_manager.received_event({
                'source': source,
                'event': 'shell_defense_enter',
            })


class EmergenceAction(Action):
    """Bonus action to emerge from shell."""

    def label(self):
        return 'Emerge from Shell'

    def __repr__(self):
        return 'EmergenceAction()'

    @staticmethod
    def can(entity, battle, options=None):
        if not battle:
            return False
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('shell_defense'):
            return False
        if not getattr(entity, '_in_shell', False):
            return False
        return True

    def build_map(self):
        return self

    def resolve(self, session, map_, opts=None):
        opts = opts or {}
        self.result = [{
            'type': 'shell_emerge',
            'source': self.source,
            'battle': opts.get('battle'),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'shell_emerge':
            return
        if session is None:
            session = battle.session if battle else None
        source = item['source']
        # Exit shell state
        source._in_shell = False
        # Remove prone (tortle stands when emerging)
        source._prone = False
        if battle:
            state = battle.entity_state_for(source)
            if state is not None:
                # Restore movement (base speed)
                state['movement'] = source.speed()
            battle.event_manager.received_event({
                'source': source,
                'event': 'shell_defense_exit',
            })
        if session:
            session.event_manager.received_event({
                'source': source,
                'event': 'shell_defense_exit',
            })
