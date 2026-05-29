from natural20.spell.spell import Spell


class HasteSpell(Spell):
    """Haste: double speed, +2 AC, extra action on turn start, concentration."""

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 30),
                'target_types': ['allies', 'enemies'],
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        if isinstance(target, list):
            target = target[0]
        return [{
            'source': entity,
            'target': target,
            'type': 'haste',
            'spell': self.properties,
            'effect': self,
        }]

    @staticmethod
    def speed_override(entity, opt=None):
        if opt is None:
            opt = {}
        return int(opt.get('value', 30)) * 2

    @staticmethod
    def ac_bonus(entity, opt=None):
        return 2

    @staticmethod
    def start_of_turn(entity, opt=None):
        battle = (opt or {}).get('battle')
        if battle is None:
            return
        state = battle.entity_state_for(entity)
        if state is not None:
            state['action'] = state.get('action', 0) + 1

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session if battle else item['source'].session
        if item.get('type') != 'haste':
            return None
        target = item['target']
        source = item['source']
        effect = item['effect']
        duration = session.game_time + int(effect.properties.get('duration_seconds', 60))

        source.add_casted_effect({'target': target, 'effect': effect, 'expiration': duration})
        if source.current_concentration() != effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        target.register_effect('speed_override', HasteSpell, effect=effect, source=source, duration=duration)
        target.register_effect('ac_bonus', HasteSpell, method_name='ac_bonus', effect=effect, source=source, duration=duration)
        target.register_event_hook('start_of_turn', HasteSpell, effect=effect, source=source)
        if 'hasted' not in target.statuses:
            target.statuses.append('hasted')

        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': effect,
            'source': source,
            'target': target,
        })
        return target
