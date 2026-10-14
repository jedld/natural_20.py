"""Arm the once-per-casting surge of a ``StrikeSurgeSpell`` (e.g. Zephyr Strike).

No action cost: the next weapon attack this turn has advantage, deals the
YAML ``extra_damage`` on a hit, and — hit or miss — adds ``speed_bonus`` feet
of movement for the rest of the turn.
"""
from __future__ import annotations

from natural20.action import Action
from natural20.utils import attack_options as ao
from natural20.utils.class_feature_registry import register_class_feature

ROUND_SECONDS = 6


class AttackSurgeEffect(ao.AttackOptionEffect):
    """Pending surge: advantage + extra damage on the next weapon attack."""

    def __init__(self, source, option):
        super().__init__(source, option)
        self.id = f"attack_surge:{option['id']}:{id(self)}"
        self.speed_granted = False

    @staticmethod
    def attack_resolved(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None or effect.rolled:
            return []
        effect.rolled = True
        bonus = int(effect.option.get('speed_bonus') or 0)
        battle = getattr(effect, 'battle', None) or _battle_for(entity)
        if bonus and battle is not None and not effect.speed_granted:
            state = battle.entity_state_for(entity)
            if state is not None:
                state['movement'] = int(state.get('movement', 0) or 0) + bonus
                effect.speed_granted = True
        return []

    @staticmethod
    def on_attack_hit(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        hit_result = opt.get('result') or {}
        if effect is None or not hit_result.get('hit?') or not ao.is_weapon_hit(entity, hit_result):
            return []
        results = []
        if effect.option.get('extra_damage'):
            results.append(ao.extra_damage_item(entity, hit_result, effect.option))
        entity.dismiss_effect(effect)
        return results


def _battle_for(entity):
    from natural20.utils.combat_comms import battle_for
    return battle_for(entity)


class AttackSurgeAction(Action):
    def __init__(self, session, source, action_type='attack_surge', opts=None):
        super().__init__(session, source, action_type, opts)

    @staticmethod
    def spell_for(entity):
        from natural20.spell.strike_surge_spell import ready_surge_spell
        return ready_surge_spell(entity)

    @staticmethod
    def can(entity, battle):
        if battle is None or AttackSurgeAction.spell_for(entity) is None:
            return False
        if battle.current_turn() is not entity:
            return False
        state = battle.entity_state_for(entity)
        if not state or (state.get('action', 0) <= 0 and not state.get('extra_attacks_remaining')):
            return False
        return _pending(entity) is None

    @staticmethod
    def build_all(session, entity, _feature_id=None, battle=None):
        if AttackSurgeAction.spell_for(entity) is None:
            return []
        return [AttackSurgeAction(session, entity)]

    def available(self, battle):
        return self.can(self.source, battle)

    def label(self):
        spell = self.spell_for(self.source)
        name = (spell.properties.get('label') or spell.properties.get('name')) if spell else 'Surge'
        return f"{name}: surge"

    def button_image(self):
        return 'attack_surge'

    def __str__(self):
        return 'AttackSurge'

    __repr__ = __str__

    def build_map(self):
        return self

    def resolve(self, session, battle_map=None, opts=None):
        spell = self.spell_for(self.source)
        self.result = [{
            'type': 'attack_surge',
            'source': self.source,
            'spell_effect': spell,
            'battle': (opts or {}).get('battle'),
        }] if spell is not None else []
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'attack_surge':
            return None
        source, spell = item['source'], item.get('spell_effect')
        if spell is None:
            return None
        session = session or (battle.session if battle is not None else source.session)
        cfg = dict(spell.surge_config())
        option = {
            'id': str(spell),
            'name': spell.properties.get('name') or str(spell),
            'advantage': bool(cfg.get('advantage', True)),
            'extra_damage': cfg.get('extra_damage'),
            'damage_type': cfg.get('damage_type'),
            'speed_bonus': cfg.get('speed_bonus', 0),
        }
        effect = AttackSurgeEffect(source, option)
        effect.battle = battle or item.get('battle')
        source.register_effect('attack_advantage_modifier', AttackSurgeEffect, effect=effect,
                               source=source, duration=ROUND_SECONDS)
        for hook in ('attack_resolved', 'on_attack_hit', 'end_of_turn'):
            source.register_event_hook(hook, AttackSurgeEffect, hook, effect=effect,
                                       source=source, duration=ROUND_SECONDS)
        spell.spend_surge(source)
        session.event_manager.received_event({
            'event': 'attack_surge', 'source': source, 'spell': option['name'],
        })
        return source


def _pending(entity):
    for entry in (getattr(entity, 'effects', None) or {}).get('attack_advantage_modifier', []) or []:
        effect = entry.get('effect')
        if isinstance(effect, AttackSurgeEffect) and not effect.rolled:
            return effect
    return None


register_class_feature(
    feature_id='attack_surge',
    action_class=AttackSurgeAction,
    provides=lambda entity: AttackSurgeAction.spell_for(entity) is not None,
    builder=lambda session, entity, feature_id, battle=None: AttackSurgeAction.build_all(
        session, entity, feature_id, battle=battle),
)
