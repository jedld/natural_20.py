from natural20.action import Action
from natural20.die_roll import DieRoll
from natural20.spell.witch_bolt_spell import WitchBoltEffect


class WitchBoltSustainAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    def clone(self):
        action = WitchBoltSustainAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        return action

    def name(self):
        return 'Sustain Witch Bolt'

    def label(self):
        return 'Sustain Witch Bolt'

    @staticmethod
    def can(entity, battle, options=None):
        if battle is None:
            return False
        if not entity.has_action(battle):
            return False
        return WitchBoltSustainAction._active_effect_entry(entity) is not None

    @staticmethod
    def _active_effect_entry(caster):
        for effect_entry in getattr(caster, 'casted_effects', []):
            effect = effect_entry.get('effect')
            if not isinstance(effect, WitchBoltEffect):
                continue
            if caster.current_concentration() is not effect:
                continue
            if not effect.is_link_valid():
                continue
            return effect_entry
        return None

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        battle = opts.get('battle')
        self.result.clear()

        effect_entry = WitchBoltSustainAction._active_effect_entry(self.source)
        if effect_entry is None:
            return self

        effect = effect_entry['effect']
        target = effect.target
        if target is None:
            return self

        self.target = target

        damage_roll = DieRoll.roll(
            "1d12",
            battle=battle,
            entity=self.source,
            description="dice_roll.spells.witch_bolt",
        )
        self.result.append(
            {
                'source': self.source,
                'target': target,
                'attack_name': "spell.witch_bolt",
                'damage_type': 'lightning',
                'damage_roll': damage_roll,
                'damage': damage_roll,
                'type': 'spell_damage',
                'spell': effect.spell_properties,
            }
        )
        self.result.append(
            {
                'type': 'witch_bolt_sustain',
                'source': self.source,
                'target': target,
                'effect': effect,
                'damage_roll': damage_roll,
            }
        )

        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'witch_bolt_sustain':
            return
        if battle and session is None:
            session = battle.session

        source = item['source']
        effect = item.get('effect')

        if battle is not None:
            battle.consume(source, 'action')

        if effect is not None:
            effect.sustained_this_turn = True

        if session is not None:
            session.event_manager.received_event(
                {
                    'event': 'witch_bolt_sustain',
                    'source': source,
                    'target': item.get('target'),
                    'damage_roll': item.get('damage_roll'),
                }
            )
