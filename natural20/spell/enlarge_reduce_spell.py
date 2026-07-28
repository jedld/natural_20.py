from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


def _str_weapon_attack(entity, context):
    weapon = context.get('weapon') or {}
    if weapon.get('type') != 'melee_attack':
        return False
    try:
        return entity.attack_ability_mod(weapon) == entity.str_mod()
    except Exception:
        return False


class EnlargeReduceSpell(Spell):
    """Enlarge/Reduce (2014): enlarge or reduce a creature (concentration, 1 minute)."""

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.mode = 'enlarge'

    def clone(self):
        spell = super().clone()
        spell.mode = self.mode
        return spell

    def build_map(self, orig_action):
        choices = [['Enlarge', 'enlarge'], ['Reduce', 'reduce']]

        def set_mode(choice):
            mode = str(choice).lower()
            if mode not in ('enlarge', 'reduce'):
                raise ValueError(f'Invalid Enlarge/Reduce mode: {choice}')

            action = orig_action.clone()
            action.spell_action.mode = mode

            def set_target(target):
                targeted = action.clone()
                targeted.target = target
                return targeted

            return {
                'param': [{
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties.get('range', 30),
                    'target_types': ['allies', 'enemies'],
                }],
                'next': set_target,
            }

        return {
            'param': [{'type': 'select_choice', 'choices': choices, 'num': 1}],
            'next': set_mode,
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        if isinstance(target, list):
            target = target[0]

        mode = getattr(spell_action.spell_action, 'mode', 'enlarge')
        save_roll = None
        dc = None
        if battle is not None and battle.opposing(entity, target):
            dc = entity.spell_save_dc('constitution')
            save_roll = target.save_throw('constitution', battle, {'is_magical': True})
            if save_roll.result() >= dc:
                return [{
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': 'enlarge_reduce',
                    'spell_save': save_roll,
                    'dc': dc,
                }]

        return [{
            'source': entity,
            'target': target,
            'type': 'enlarge_reduce',
            'mode': mode,
            'spell': self.properties,
            'effect': self,
            'spell_save': save_roll,
            'dc': dc,
        }]

    @staticmethod
    def size_override(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        mode = getattr(effect, 'mode', 'enlarge') if effect else 'enlarge'
        return 'large' if mode == 'enlarge' else 'small'

    @staticmethod
    def _apply_damage_modifier(target, effect, mode):
        if mode == 'enlarge':
            target.add_modifier(
                'damage_roll',
                effect,
                value='1d4',
                condition=_str_weapon_attack,
            )
        else:
            def penalty(entity, context):
                if not _str_weapon_attack(entity, context):
                    return None
                battle = context.get('battle')
                roll = DieRoll.roll(
                    '1d4',
                    description='enlarge_reduce_reduce',
                    entity=entity,
                    battle=battle,
                )
                return -roll.result()

            target.add_modifier('damage_roll', effect, value=penalty)

    @staticmethod
    def _apply_save_modifiers(target, effect, mode):
        if mode == 'enlarge':
            target.add_modifier(
                'save_roll',
                effect,
                value=0,
                advantage=True,
                condition=lambda _e, ctx: (ctx or {}).get('ability') == 'strength',
            )
        else:
            target.add_modifier(
                'save_roll',
                effect,
                value=0,
                disadvantage=True,
                condition=lambda _e, ctx: (ctx or {}).get('ability') == 'strength',
            )

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session if battle else item['source'].session
        if item.get('type') != 'enlarge_reduce':
            return None

        target = item['target']
        source = item['source']
        effect = item['effect']
        mode = item.get('mode', getattr(effect, 'mode', 'enlarge'))
        effect.mode = mode
        duration = session.game_time + int(effect.properties.get('duration_seconds', 60))

        source.add_casted_effect({'target': target, 'effect': effect, 'expiration': duration})
        if source.current_concentration() != effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        target.register_effect(
            'size_override', EnlargeReduceSpell,
            method_name='size_override', effect=effect, source=source, duration=duration,
        )
        EnlargeReduceSpell._apply_damage_modifier(target, effect, mode)
        EnlargeReduceSpell._apply_save_modifiers(target, effect, mode)

        status = 'enlarged' if mode == 'enlarge' else 'reduced'
        if status not in target.statuses:
            target.statuses.append(status)

        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': effect,
            'source': source,
            'target': target,
        })
        return target

    def dismiss(self, entity, _descriptor=None, _opts=None):
        try:
            entity.remove_modifier(self)
        except Exception:
            pass
        for status in ('enlarged', 'reduced'):
            if status in getattr(entity, 'statuses', []):
                entity.statuses.remove(status)
