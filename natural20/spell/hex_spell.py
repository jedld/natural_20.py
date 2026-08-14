"""Hex — 1st-level warlock enchantment (SRD 5.2). Extra 1d6 necrotic on hits + ability check disadv."""

from natural20.spell.spell import Spell


_ABILITY_CHOICES = (
    ('Strength', 'str'),
    ('Dexterity', 'dex'),
    ('Constitution', 'con'),
    ('Intelligence', 'int'),
    ('Wisdom', 'wis'),
    ('Charisma', 'cha'),
)


class HexSpell(Spell):
    DURATION_SECONDS = 60 * 60  # 1 hour base; upcast extends via apply

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self._instance_id = f"hex:{id(self)}"
        self.marked_target = None
        self.hexed_ability = 'str'

    @property
    def id(self):
        return self._instance_id

    def build_map(self, orig_action):
        def set_ability(choice):
            ability = str(choice).lower()
            if ability not in {a for _, a in _ABILITY_CHOICES}:
                raise ValueError(f'Invalid Hex ability: {choice}')
            action = orig_action.clone()
            action.spell_action.hexed_ability = ability

            def set_target(target):
                action2 = action.clone()
                action2.target = target
                return action2

            return {
                'param': [
                    {
                        'type': 'select_target',
                        'num': 1,
                        'range': self.properties.get('range', 90),
                        'target_types': ['enemies'],
                    }
                ],
                'next': set_target,
            }

        return {
            'param': [
                {
                    'type': 'select_choice',
                    'choices': [[label, value] for label, value in _ABILITY_CHOICES],
                    'num': 1,
                }
            ],
            'next': set_ability,
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        if isinstance(target, list):
            target = target[0]
        ability = getattr(
            getattr(spell_action, 'spell_action', None),
            'hexed_ability',
            self.hexed_ability,
        )
        return [{
            'type': 'hex',
            'source': entity,
            'target': target,
            'spell': self.properties,
            'effect': self,
            'hexed_ability': ability,
            'cast_level': getattr(spell_action, 'at_level', 1),
        }]

    @staticmethod
    def _duration_seconds(cast_level: int) -> int:
        level = int(cast_level or 1)
        if level >= 5:
            return 24 * 60 * 60
        if level >= 3:
            return 8 * 60 * 60
        if level >= 2:
            return 4 * 60 * 60
        return HexSpell.DURATION_SECONDS

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'hex':
            return
        if battle and session is None:
            session = battle.session

        source = item['source']
        target = item['target']
        effect = item['effect']
        effect.marked_target = target
        effect.hexed_ability = item.get('hexed_ability', 'str')
        duration = HexSpell._duration_seconds(item.get('cast_level', 1))

        if source.has_effect('hex'):
            for desc in list(source.effects.get('hex', [])):
                source.dismiss_effect(desc['effect'])

        # Extra necrotic on attack hits vs marked target (weapon AttackAction path).
        source.add_modifier(
            'damage_roll',
            effect,
            value='1d6',
            condition=lambda _e, ctx, _eff=effect: (
                ctx.get('target') is _eff.marked_target
            ),
        )

        target.register_effect(
            'ability_check_advantage_modifier',
            effect,
            method_name='ability_check_advantage_modifier',
            effect=effect,
            source=source,
            duration=duration,
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
                'expiration': session.game_time + duration,
            })

        source.register_effect(
            'hex', HexSpell,
            effect=effect, source=source, duration=duration,
        )

        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_debuff',
                'spell': effect,
                'source': source,
                'target': target,
            })

    def ability_check_advantage_modifier(self, entity, opt=None):
        opt = opt or {}
        ability = self.hexed_ability
        check_ability = opt.get('ability')
        skill = opt.get('skill')
        if check_ability is None and skill and hasattr(entity, 'SKILL_AND_ABILITY_MAP'):
            for ab, skills in entity.SKILL_AND_ABILITY_MAP.items():
                if skill in skills:
                    check_ability = ab
                    break
        if check_ability is not None and check_ability != ability:
            return [[], []]
        return [[], ['hex']]

    def dismiss(self, entity, _descriptor=None, _opts=None):
        try:
            entity.remove_modifier(self)
        except Exception:
            pass
        target = self.marked_target
        if target is not None:
            try:
                target.dismiss_effect(self)
            except Exception:
                pass
