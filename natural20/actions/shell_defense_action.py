"""Tortle racial trait - Shell Defense (Monsters of the Multiverse).

Withdraw into your shell as an action. Until you emerge:
- +4 bonus to AC
- Advantage on Strength and Constitution saving throws
- Disadvantage on Dexterity saving throws
- Prone, speed 0 (can't increase)
- No reactions
- The only action you can take is a bonus action to emerge
"""

from natural20.action import Action


class ShellDefenseEffect:
    """Lightweight effect marker so map tiles can show the shell icon."""

    id = 'shell_defense'

    def __str__(self):
        return 'shell_defense'

    def __repr__(self):
        return 'ShellDefenseEffect()'


class ShellDefenseAction(Action):
    def label(self):
        return 'Shell Defense: Withdraw'

    def __repr__(self):
        return 'ShellDefense()'

    def button_label(self):
        return 'Shell Defense'

    def button_image(self):
        return 'shell_defense'

    @staticmethod
    def can(entity, battle, options=None):
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('shell_defense'):
            return False
        if getattr(entity, '_in_shell', False):
            return False
        if battle is None:
            return True
        return entity.total_actions(battle) > 0

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
        source._in_shell = True
        if hasattr(source, 'do_prone'):
            source.do_prone()
        # Register a display effect for map overlays.
        effect = ShellDefenseEffect()
        source._shell_defense_effect = effect
        if hasattr(source, 'register_effect'):
            source.register_effect(
                'shell_defense',
                ShellDefenseAction,
                method_name='shell_defense_marker',
                effect=effect,
                source=source,
            )
        if battle:
            state = battle.entity_state_for(source)
            if state is not None:
                state['movement'] = 0
            battle.consume(source, 'action')
            battle.event_manager.received_event({
                'source': source,
                'event': 'shell_defense_enter',
            })
        if session:
            session.event_manager.received_event({
                'source': source,
                'event': 'shell_defense_enter',
            })

    @staticmethod
    def shell_defense_marker(entity, opt=None):
        return True


class EmergenceAction(Action):
    """Bonus action to emerge from shell."""

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    def label(self):
        return 'Shell Defense: Emerge'

    def __repr__(self):
        return 'EmergenceAction()'

    def button_label(self):
        return 'Emerge'

    def button_image(self):
        return 'shell_defense'

    @staticmethod
    def can(entity, battle, options=None):
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('shell_defense'):
            return False
        if not getattr(entity, '_in_shell', False):
            return False
        if battle is None:
            return True
        return entity.total_bonus_actions(battle) > 0

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
        source._in_shell = False
        effect = getattr(source, '_shell_defense_effect', None)
        if effect is not None and hasattr(source, 'remove_effect'):
            source.remove_effect(effect)
            source._shell_defense_effect = None
        elif hasattr(source, 'effects'):
            for effect_type, entries in list(source.effects.items()):
                source.effects[effect_type] = [
                    e for e in entries
                    if getattr(e.get('effect'), 'id', None) != 'shell_defense'
                ]
        if hasattr(source, 'stand') and source.prone():
            try:
                source.stand()
            except Exception:
                if 'prone' in getattr(source, 'statuses', []):
                    source.statuses.remove('prone')
        if battle:
            state = battle.entity_state_for(source)
            if state is not None:
                state['movement'] = source.speed()
            battle.consume(source, 'bonus_action')
            battle.event_manager.received_event({
                'source': source,
                'event': 'shell_defense_exit',
            })
        if session:
            session.event_manager.received_event({
                'source': source,
                'event': 'shell_defense_exit',
            })
