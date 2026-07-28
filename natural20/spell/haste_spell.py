from natural20.spell.spell import Spell


class HasteSpell(Spell):
    """Haste (2014): willing ally gains double speed, +2 AC, DEX save advantage, extra action."""

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
                'target_types': ['allies', 'self'],
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
        opt = opt or {}
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
    def lethargy_start_of_turn(entity, opt=None):
        battle = (opt or {}).get('battle')
        if battle is None or 'haste_lethargy' not in getattr(entity, 'statuses', []):
            return
        state = battle.entity_state_for(entity)
        if state is not None:
            state['action'] = 0
            state['bonus_action'] = 0
            state['movement'] = 0

    @staticmethod
    def lethargy_end_of_turn(entity, opt=None):
        if 'haste_lethargy' in getattr(entity, 'statuses', []):
            entity.statuses.remove('haste_lethargy')

    @staticmethod
    def apply_lethargy(target, battle=None):
        if 'haste_lethargy' not in target.statuses:
            target.statuses.append('haste_lethargy')
        target.register_event_hook('start_of_turn', HasteSpell, method_name='lethargy_start_of_turn')
        target.register_event_hook('end_of_turn', HasteSpell, method_name='lethargy_end_of_turn')

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
        target.add_modifier(
            'save_roll',
            effect,
            value=0,
            advantage=True,
            condition=lambda _e, ctx: (ctx or {}).get('ability') == 'dexterity',
        )
        if 'hasted' not in target.statuses:
            target.statuses.append('hasted')

        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': effect,
            'source': source,
            'target': target,
        })
        return target

    def dismiss(self, entity, _descriptor=None, opts=None):
        opts = opts or {}
        try:
            entity.remove_modifier(self)
        except Exception:
            pass
        if 'hasted' in getattr(entity, 'statuses', []):
            entity.statuses.remove('hasted')
        HasteSpell.apply_lethargy(entity, battle=opts.get('battle'))
