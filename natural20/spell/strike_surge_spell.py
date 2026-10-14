"""Self-buff spells that make the caster slippery and grant one empowered strike.

Generic engine support for "move like the wind" spells (e.g. the Zephyr
Strike spell in the ``xanathars_guide`` expansion pack). Spell YAML::

    no_opportunity_attacks: true    # your movement provokes no opportunity attacks
    attack_surge:                   # once per casting, on your turn
      advantage: true               # advantage on one weapon attack roll
      extra_damage: 1d8             # added on a hit
      damage_type: force
      speed_bonus: 30               # extra movement this turn, hit or miss

The caster arms the surge with ``AttackSurgeAction`` (no action cost); see
``natural20/actions/attack_surge_action.py``.
"""
from __future__ import annotations

from natural20.spell.spell import Spell

READY_EFFECT = 'attack_surge_ready'


class StrikeSurgeSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.surge_used = False

    def __str__(self):
        return str((self.properties or {}).get('id') or 'strike_surge')

    def surge_config(self):
        cfg = (self.properties or {}).get('attack_surge')
        return cfg if isinstance(cfg, dict) else {}

    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = self.source
        return action

    def resolve(self, entity, battle, spell_action, battle_map):
        return [{
            'type': 'strike_surge',
            'source': entity,
            'target': entity,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def no_opportunity_attacks(entity, opts=None):
        return True

    @staticmethod
    def attack_surge_ready(entity, opts=None):
        return True

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'strike_surge':
            return None
        source, effect = item['source'], item['effect']
        session = session or (battle.session if battle is not None else source.session)
        duration = int(effect.properties.get('duration_seconds', 60))
        if effect.properties.get('concentration'):
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)
        source.add_casted_effect({'target': source, 'effect': effect,
                                  'expiration': session.game_time + duration})
        if effect.properties.get('no_opportunity_attacks'):
            source.register_effect('no_opportunity_attacks', StrikeSurgeSpell, effect=effect,
                                   source=source, duration=duration)
        if effect.surge_config():
            source.register_effect(READY_EFFECT, StrikeSurgeSpell, effect=effect, source=source,
                                   duration=duration)
        session.event_manager.received_event({
            'event': 'spell_buf', 'spell': effect, 'source': source, 'target': source,
        })
        return source

    def spend_surge(self, entity):
        self.surge_used = True
        effects = entity.effects.get(READY_EFFECT) or []
        kept = [f for f in effects if f.get('effect') is not self]
        if kept:
            entity.effects[READY_EFFECT] = kept
        else:
            entity.effects.pop(READY_EFFECT, None)


def ready_surge_spell(entity):
    """The active ``StrikeSurgeSpell`` whose surge ``entity`` can still use, or None."""
    session = getattr(entity, 'session', None)
    now = getattr(session, 'game_time', 0) if session is not None else 0
    for entry in (getattr(entity, 'effects', None) or {}).get(READY_EFFECT, []) or []:
        effect = entry.get('effect')
        expiration = entry.get('expiration')
        if expiration is not None and expiration <= now:
            continue
        if isinstance(effect, StrikeSurgeSpell) and not effect.surge_used:
            return effect
    return None
