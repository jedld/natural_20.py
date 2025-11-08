from natural20.die_roll import Rollable
from natural20.spell.spell import Spell
from natural20.utils.attack_util import damage_event


class _FixedRoll(Rollable):
    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value

    def __repr__(self):
        return str(self._value)


class ArmorOfAgathysSpell(Spell):
    DURATION_SECONDS = 60 * 60

    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = action.source
        return action

    def resolve(self, entity, battle, spell_action, _battle_map):
        temp_hp_amount = self._temp_hp_amount()
        self.temp_hp_granted = temp_hp_amount
        return [{
            'type': 'armor_of_agathys',
            'target': spell_action.source,
            'source': spell_action.source,
            'effect': self,
            'spell': self.properties,
            'temp_hp': temp_hp_amount
        }]

    def _temp_hp_amount(self):
        cast_level = getattr(self.action, 'at_level', self.properties.get('level', 1))
        if cast_level is None or cast_level < 1:
            cast_level = 1
        return 5 * cast_level

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'armor_of_agathys':
            return

        if battle and session is None:
            session = battle.session
        if session is None:
            session = item['source'].session if item['source'] else None

        effect = item['effect']
        source = item['source']
        target = item['target']
        temp_hp_amount = item.get('temp_hp', 0)
        effect.temp_hp_granted = temp_hp_amount

        if target.has_spell_effect('armor_of_agathys'):
            target.dismiss_effect('armor_of_agathys')

        target.grant_temp_hp(temp_hp_amount, source=source, effect=effect)

        if session:
            source.add_casted_effect({
                'target': target,
                'effect': effect,
                'expiration': session.game_time + ArmorOfAgathysSpell.DURATION_SECONDS
            })

        target.register_effect(
            'armor_of_agathys',
            ArmorOfAgathysSpell,
            effect=effect,
            source=source,
            duration=ArmorOfAgathysSpell.DURATION_SECONDS
        )
        target.register_event_hook(
            'damage',
            ArmorOfAgathysSpell,
            effect=effect,
            source=source,
            duration=ArmorOfAgathysSpell.DURATION_SECONDS
        )
        target.register_event_hook(
            'temp_hp_depleted',
            ArmorOfAgathysSpell,
            effect=effect,
            source=source
        )

        if session:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': source,
                'target': target
            })

    @staticmethod
    def damage(entity, opts=None):
        if opts is None:
            opts = {}

        effect = opts.get('effect')
        if not isinstance(effect, ArmorOfAgathysSpell):
            return

        if entity.temp_hp() <= 0:
            return

        attacker = opts.get('attacker')
        if attacker is None or attacker == entity:
            return

        attack_payload = opts.get('item')
        if not ArmorOfAgathysSpell._is_melee_attack(attack_payload):
            return

        cold_damage = getattr(effect, 'temp_hp_granted', 0)
        if cold_damage <= 0:
            return

        retaliation = {
            'source': entity,
            'target': attacker,
            'attack_name': 'Armor of Agathys',
            'damage_type': 'cold',
            'damage': _FixedRoll(cold_damage),
            'damage_roll': _FixedRoll(cold_damage),
            'advantage_mod': 0,
            'adv_info': None,
            'thrown': False,
            'spell': effect.properties,
            'sneak_attack': None
        }

        damage_event(retaliation, opts.get('battle'))

    @staticmethod
    def temp_hp_depleted(entity, opts=None):
        if opts is None:
            opts = {}

        effect = opts.get('effect')
        if not isinstance(effect, ArmorOfAgathysSpell):
            return

        entity.dismiss_effect(effect)

    def dismiss(self, entity, _descriptor, _opts=None):
        entity.clear_temp_hp(effect=self)

    @staticmethod
    def _is_melee_attack(item):
        if not item:
            return False

        if item.get('thrown'):
            return False

        weapon = item.get('weapon')
        if isinstance(weapon, dict) and weapon.get('type') == 'melee_attack':
            return True

        spell = item.get('spell')
        if isinstance(spell, dict) and spell.get('type') == 'melee_attack':
            return True

        context = item.get('context')
        if isinstance(context, dict) and context.get('type') == 'melee_attack':
            return True

        return False
