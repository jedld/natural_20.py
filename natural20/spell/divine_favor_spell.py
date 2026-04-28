from natural20.spell.spell import Spell


class DivineFavorSpell(Spell):
    """Divine Favor (paladin 1st-level evocation, concentration, 1 minute).

    Until the spell ends, the caster's weapon attacks deal an extra 1d4
    radiant damage on a hit.
    """

    DURATION_SECONDS = 60

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self._instance_id = f"divine_favor:{id(self)}"

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
        }

    @staticmethod
    def from_dict(data):
        spell = DivineFavorSpell(data['session'], data['source'], data['name'], data['properties'])
        spell.action = data['action']
        return spell

    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = action.source
        return action

    def resolve(self, entity, battle, spell_action, _battle_map):
        return [{
            'type': 'divine_favor',
            'source': entity,
            'target': entity,
            'spell': self.properties,
            'effect': self,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'divine_favor':
            return
        if battle and session is None:
            session = battle.session

        source = item['source']
        effect = item['effect']

        # Drop any prior Divine Favor (same caster only allows one).
        if source.has_spell_effect('divine_favor'):
            source.dismiss_effect('divine_favor')

        # Damage modifier: extra 1d4 radiant on weapon attacks.
        source.add_modifier(
            'damage_roll',
            effect,
            value='1d4',
            condition=lambda _e, ctx: ctx.get('weapon') is not None,
        )

        if not source.current_concentration() == effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        if session is not None:
            source.add_casted_effect({
                'target': source,
                'effect': effect,
                'expiration': session.game_time + DivineFavorSpell.DURATION_SECONDS,
            })

        source.register_effect(
            'divine_favor', DivineFavorSpell,
            effect=effect, source=source,
            duration=DivineFavorSpell.DURATION_SECONDS,
        )

        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': source,
                'target': source,
            })

    def dismiss(self, entity, _descriptor=None, _opts=None):
        try:
            entity.remove_modifier(self)
        except Exception:
            pass
