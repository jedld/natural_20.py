from natural20.spell.spell import Spell


class HuntersMarkSpell(Spell):
    """Hunter's Mark (ranger 1st-level divination, concentration, 1 hour).

    Mark a target. Until the spell ends, the caster deals an extra 1d6
    damage on weapon attacks against the marked target.
    """

    DURATION_SECONDS = 60 * 60

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self._instance_id = f"hunters_mark:{id(self)}"
        self.marked_target = None

    @property
    def id(self):
        return self._instance_id

    def to_dict(self):
        return {
            'name': self.name,
            'action': self.action,
            'session': self.session,
            'properties': self.properties,
            'source': self.source.entity_uid,
            'marked_target': self.marked_target.entity_uid if self.marked_target else None,
        }

    @staticmethod
    def from_dict(data):
        spell = HuntersMarkSpell(data['session'], data['source'], data['name'], data['properties'])
        spell.action = data['action']
        return spell

    def build_map(self, orig_action):
        def set_target(target):
            if not target:
                raise ValueError("Invalid target")
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies'],
                }
            ],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        if isinstance(target, list):
            target = target[0]
        return [{
            'type': 'hunters_mark',
            'source': entity,
            'target': target,
            'spell': self.properties,
            'effect': self,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'hunters_mark':
            return
        if battle and session is None:
            session = battle.session

        source = item['source']
        target = item['target']
        effect = item['effect']
        effect.marked_target = target

        # Drop any prior Hunter's Mark from this caster.
        if source.has_spell_effect('hunters_mark'):
            source.dismiss_effect('hunters_mark')

        source.add_modifier(
            'damage_roll',
            effect,
            value='1d6',
            condition=lambda _e, ctx, _eff=effect: (
                ctx.get('weapon') is not None
                and ctx.get('target') is _eff.marked_target
            ),
        )

        if not source.current_concentration() == effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        if session is not None:
            source.add_casted_effect({
                'target': target,
                'effect': effect,
                'expiration': session.game_time + HuntersMarkSpell.DURATION_SECONDS,
            })

        source.register_effect(
            'hunters_mark', HuntersMarkSpell,
            effect=effect, source=source,
            duration=HuntersMarkSpell.DURATION_SECONDS,
        )

        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': source,
                'target': target,
            })

    def dismiss(self, entity, _descriptor=None, _opts=None):
        try:
            entity.remove_modifier(self)
        except Exception:
            pass
