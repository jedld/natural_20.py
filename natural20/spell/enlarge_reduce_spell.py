from natural20.spell.spell import Spell


class EnlargeReduceSpell(Spell):
    """Enlarge/Reduce (enlarge mode): +1d4 STR, Large size, concentration."""

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
            'type': 'enlarge_reduce',
            'mode': 'enlarge',
            'spell': self.properties,
            'effect': self,
        }]

    @staticmethod
    def strength_override(entity, opt=None):
        if opt is None:
            opt = {}
        base = opt.get('strength') or opt.get('value') or 10
        bonus = opt.get('effect').properties.get('enlarge_bonus', 2) if opt.get('effect') else 2
        return base + bonus

    @staticmethod
    def size_override(entity, opt=None):
        return 'large'

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session if battle else item['source'].session
        if item.get('type') != 'enlarge_reduce':
            return None
        target = item['target']
        source = item['source']
        effect = item['effect']
        duration = session.game_time + int(item['effect'].properties.get('duration_seconds', 60))

        source.add_casted_effect({'target': target, 'effect': effect, 'expiration': duration})
        if source.current_concentration() != effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        target.register_effect('strength_override', EnlargeReduceSpell, effect=effect, source=source, duration=duration)
        target.register_effect('size_override', EnlargeReduceSpell, method_name='size_override', effect=effect, source=source, duration=duration)
        if 'enlarged' not in target.statuses:
            target.statuses.append('enlarged')

        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': effect,
            'source': source,
            'target': target,
        })
        return target
