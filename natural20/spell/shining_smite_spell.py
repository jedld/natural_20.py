"""Shining Smite — 2nd-level paladin transmutation (SRD 5.2).

Bonus Action taken right after hitting with a melee weapon or an Unarmed
Strike: the target takes an extra 2d6 radiant damage (+1d6 per slot level
above 2nd, doubled on a critical hit). While the caster concentrates (up to
1 minute) the target sheds dim light in a 5-foot radius, attack rolls against
it have advantage, and it can't benefit from the Invisible condition.

Offered through ``ShiningSmiteOffer`` (an ``on_attack_hit`` hook registered by
``Paladin.initialize_paladin``) whenever the spell is prepared. It has no 2014
counterpart, so unlike Searing Smite it is not limited to the 5e-2024 ruleset.

Target-side effects registered while the spell lasts:

* ``targeted_advantage_override`` — attackers get advantage (read by
  ``natural20.weapons.compute_advantages_and_disadvantages``).
* ``light_override`` — dim light 5 ft (read by ``Entity.light_properties``).
* ``invisibility_suppressed`` — marker for "can't benefit from Invisible".
"""
from __future__ import annotations

from natural20.spell.extensions.post_hit_smite import PostHitSmiteAction, PostHitSmiteOffer
from natural20.spell.spell import Spell


class ShiningSmiteAction(PostHitSmiteAction):
    SPELL_ID = 'shining_smite'
    BASE_DICE = 2
    DAMAGE_TYPE = 'radiant'

    def rider_items(self, battle, damage_roll):
        effect = ShiningSmiteSpell(self.session, self.source, 'ShiningSmiteSpell', self.spell_details)
        effect.target = self.target
        effect.cast_level = self.slot_level
        return [{
            'type': 'shining_smite',
            'source': self.source,
            'target': self.target,
            'effect': effect,
            'spell': self.spell_details,
        }]


class ShiningSmiteOffer(PostHitSmiteOffer):
    SPELL_ID = 'shining_smite'
    ACTION_CLASS = ShiningSmiteAction


class ShiningSmiteSpell(Spell):
    DURATION_SECONDS = 60
    DIM_LIGHT_FEET = 5
    TARGET_EFFECTS = ('targeted_advantage_override', 'light_override', 'invisibility_suppressed')

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.cast_level = int((details or {}).get('level') or 2)
        self._instance_id = f"shining_smite:{id(self)}"

    @property
    def id(self):
        return self._instance_id

    def __str__(self):
        return 'shining_smite'

    def build_map(self, orig_action):
        # Cast through the post-hit bonus-action offer; a direct cast is a no-op.
        return orig_action

    def resolve(self, entity, battle, spell_action, battle_map):
        return []

    @staticmethod
    def targeted_advantage_override(entity, opt=None):
        return [['shining_smite'], []]

    @staticmethod
    def light_override(entity, opt=None):
        opt = opt or {}
        return {
            'bright': opt.get('bright', 0) or 0,
            'dim': max(opt.get('dim', 0) or 0, ShiningSmiteSpell.DIM_LIGHT_FEET),
        }

    @staticmethod
    def invisibility_suppressed(entity, opt=None):
        return True

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'shining_smite':
            return None
        if battle is not None and session is None:
            session = battle.session
        source = item['source']
        target = item['target']
        effect = item['effect']
        effect.target = target
        duration = ShiningSmiteSpell.DURATION_SECONDS

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
        for effect_type in ShiningSmiteSpell.TARGET_EFFECTS:
            target.register_effect(effect_type, ShiningSmiteSpell, effect=effect,
                                   source=source, duration=duration)
        battle_map = battle.map_for(target) if battle is not None else None
        if battle_map is not None and hasattr(battle_map, 'invalidate_dynamic_lights'):
            battle_map.invalidate_dynamic_lights()

        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_debuff',
                'spell': effect,
                'source': source,
                'target': target,
            })
        return target

    def dismiss(self, entity, _descriptor=None, opts=None):
        target = self.target
        if target is not None and entity is not target and hasattr(target, 'remove_effect'):
            target.remove_effect(self)
            battle_map = None
            session = getattr(target, 'session', None)
            if session is not None and hasattr(session, 'map_for'):
                try:
                    battle_map = session.map_for(target)
                except Exception:
                    battle_map = None
            if battle_map is not None and hasattr(battle_map, 'invalidate_dynamic_lights'):
                battle_map.invalidate_dynamic_lights()
        source = self.source
        if source is not None and getattr(source, 'concentration', None) is self:
            source.drop_concentration()
