"""Channel Divinity: Sacred Weapon (Oath of Devotion, SRD).

For the duration the paladin adds their Charisma modifier (minimum +1) to
attack rolls with the imbued weapon, and the weapon sheds bright light in a
20-foot radius and dim light 20 feet beyond.

Edition timing (``Ruleset.sacred_weapon_model``):

* ``action`` (2014): costs an action, lasts 1 minute.
* ``attack_action`` (2024): taken as part of the Attack action (no extra
  action cost, but the action must still be available), lasts 10 minutes.

The effect ends early if the paladin is unconscious (it stops applying).
"""

from natural20.action import Action
from natural20.utils.class_feature_registry import register_class_feature


def _sacred_weapon_model(session):
    ruleset = getattr(session, 'ruleset', None)
    try:
        return ruleset.sacred_weapon_model() if ruleset is not None else 'action'
    except Exception:
        return 'action'


def _imbuable_weapon(entity):
    session = entity.session
    fallback = None
    for name in entity.properties.get('equipped', []) or []:
        weapon = session.load_weapon(name)
        if not weapon or weapon.get('type') not in ('melee_attack', 'ranged_attack'):
            continue
        if weapon.get('type') == 'melee_attack':
            return name
        fallback = fallback or name
    return fallback


class SacredWeaponEffect:
    BRIGHT_FEET = 20
    DIM_FEET = 40

    def __init__(self, source, weapon, bonus):
        self.source = source
        self.target = source
        self.action = None
        self.weapon = weapon
        self.bonus = int(bonus)
        self.id = f"sacred_weapon:{id(self)}"

    def __str__(self):
        return 'sacred_weapon'

    @staticmethod
    def attack_roll_bonus(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        value = opt.get('value') or 0
        if effect is None or not entity.conscious():
            return value
        weapon = opt.get('weapon_name')
        if weapon is not None and effect.weapon is not None and weapon != effect.weapon:
            return value
        return value + effect.bonus

    @staticmethod
    def light_override(entity, opt=None):
        opt = opt or {}
        return {
            'bright': max(opt.get('bright', 0) or 0, SacredWeaponEffect.BRIGHT_FEET),
            'dim': max(opt.get('dim', 0) or 0, SacredWeaponEffect.DIM_FEET),
        }


class SacredWeaponAction(Action):
    @staticmethod
    def can(entity, battle):
        if not entity.class_feature('sacred_weapon'):
            return False
        if not getattr(entity, 'has_channel_divinity', None) or not entity.has_channel_divinity():
            return False
        if _imbuable_weapon(entity) is None:
            return False
        if entity.has_effect('attack_roll_bonus') and any(
                str(e.get('effect')) == 'sacred_weapon' for e in entity.effects.get('attack_roll_bonus', [])):
            return False
        if battle is None:
            return True
        state = battle.entity_state_for(entity)
        return bool(state) and state.get('action', 0) > 0

    def label(self):
        uses = getattr(self.source, 'channel_divinity_count', 0)
        return f"Channel Divinity: Sacred Weapon ({uses})"

    def __str__(self):
        return "SacredWeapon"

    __repr__ = __str__

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        return SacredWeaponAction(session, source, 'channel_divinity_sacred_weapon').build_map()

    def resolve(self, session, battle_map=None, opts=None):
        battle = (opts or {}).get('battle')
        model = _sacred_weapon_model(self.session)
        self.result = [{
            'type': 'sacred_weapon',
            'source': self.source,
            'weapon': _imbuable_weapon(self.source),
            'bonus': max(1, int(self.source.cha_mod() or 0)),
            'duration': 600 if model == 'attack_action' else 60,
            'action_cost': None if model == 'attack_action' else 'action',
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'sacred_weapon':
            return
        if session is None and battle is not None:
            session = battle.session
        source = item['source']
        effect = SacredWeaponEffect(source, item.get('weapon'), item.get('bonus', 1))
        duration = item.get('duration', 60)
        source.register_effect('attack_roll_bonus', SacredWeaponEffect, effect=effect,
                               source=source, duration=duration)
        source.register_effect('light_override', SacredWeaponEffect, effect=effect,
                               source=source, duration=duration)
        if hasattr(source, 'channel_divinity'):
            source.channel_divinity()
        if battle is not None and item.get('action_cost'):
            battle.consume(source, item['action_cost'])
        if session is not None:
            session.event_manager.received_event({
                'event': 'sacred_weapon',
                'source': source,
                'weapon': item.get('weapon'),
                'bonus': item.get('bonus'),
            })


register_class_feature(
    feature_id='channel_divinity_sacred_weapon',
    action_class=SacredWeaponAction,
)
