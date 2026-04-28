from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll


class FalseLifeSpell(Spell):
    """False Life (necromancy 1st level, self, 1 hour).

    Gain ``1d4 + 4`` temporary hit points; +5 per slot above 1st.
    """

    DURATION_SECONDS = 60 * 60

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self._instance_id = f"false_life:{id(self)}"
        self.temp_hp_granted = 0

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
            'temp_hp_granted': self.temp_hp_granted,
        }

    @staticmethod
    def from_dict(data):
        spell = FalseLifeSpell(data['session'], data['source'], data['name'], data['properties'])
        spell.action = data['action']
        spell.temp_hp_granted = data.get('temp_hp_granted', 0)
        return spell

    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = action.source
        return action

    def _temp_hp(self, battle):
        cast_level = getattr(self.action, 'at_level', self.properties.get('level', 1)) if self.action else 1
        if cast_level is None or cast_level < 1:
            cast_level = 1
        roll = DieRoll.roll(
            '1d4', battle=battle, entity=self.source,
            description='dice_roll.spells.false_life',
        )
        return int(roll.result()) + 4 + 5 * (cast_level - 1)

    def resolve(self, entity, battle, spell_action, _battle_map):
        amount = self._temp_hp(battle)
        self.temp_hp_granted = amount
        return [{
            'type': 'false_life',
            'source': entity,
            'target': entity,
            'spell': self.properties,
            'effect': self,
            'temp_hp': amount,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'false_life':
            return
        if battle and session is None:
            session = battle.session
        if session is None:
            session = item['source'].session if item['source'] else None

        source = item['source']
        effect = item['effect']
        amount = item.get('temp_hp', 0)
        effect.temp_hp_granted = amount

        if source.has_spell_effect('false_life'):
            source.dismiss_effect('false_life')

        source.grant_temp_hp(amount, source=source, effect=effect)

        if session is not None:
            source.add_casted_effect({
                'target': source,
                'effect': effect,
                'expiration': session.game_time + FalseLifeSpell.DURATION_SECONDS,
            })

        source.register_effect(
            'false_life', FalseLifeSpell,
            effect=effect, source=source,
            duration=FalseLifeSpell.DURATION_SECONDS,
        )
        source.register_event_hook(
            'temp_hp_depleted', FalseLifeSpell,
            effect=effect, source=source,
        )

        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': source,
                'target': source,
            })

    @staticmethod
    def temp_hp_depleted(entity, opts=None):
        effect = (opts or {}).get('effect')
        if not isinstance(effect, FalseLifeSpell):
            return
        try:
            entity.dismiss_effect(effect)
        except Exception:
            pass

    def dismiss(self, entity, _descriptor=None, _opts=None):
        try:
            entity.clear_temp_hp(effect=self)
        except Exception:
            pass
