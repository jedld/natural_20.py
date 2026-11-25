from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack, spell_attack_is_critical
from natural20.spell.extensions.hit_computations import AttackSpell


def _purge_hooks(holder, effect):
    """Drop every event hook on *holder* that points at *effect*."""
    if holder is None:
        return
    hooks = getattr(holder, 'entity_event_hooks', None)
    if not hooks:
        return
    for event_type, entries in list(hooks.items()):
        kept = [h for h in entries if h.get('effect') is not effect]
        if len(kept) != len(entries):
            hooks[event_type] = kept


class ChillTouchSpellUndeadEffect:
    """Undead hit by Chill Touch: disadvantage on attacks vs the caster
    until the *end* of the caster's next turn (2014 PHB).

    Uses a unique per-instance id so dismissing this rider never collides
    with the heal-block effect (YAML id ``chill_touch``) via remove_effect's
    id-fallback path.
    """

    def __init__(self, source, target):
        self.source = source
        self.target = target
        self._instance_id = f'chill_touch_undead:{id(self)}'

    @property
    def id(self):
        return self._instance_id

    def __str__(self):
        return 'chill_touch_undead'

    def dismiss(self, entity, _descriptor=None, opts=None):
        _purge_hooks(self.source, self)
        _purge_hooks(self.target, self)

    @staticmethod
    def attack_advantage_modifier(entity, opt=None):
        if opt['target'] == opt['effect'].source:
            return [[], ['chill_touch_disadvantage']]
        return [[], []]

    @staticmethod
    def end_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        # Identity-only removal: never fall back to a shared spell id.
        opts = {'_allow_id_fallback': False}
        if effect.target is not None:
            effect.target.remove_effect(effect, opts)
        if effect.source is not None and effect.source is not effect.target:
            effect.source.remove_effect(effect, opts)
        _purge_hooks(effect.source, effect)
        _purge_hooks(effect.target, effect)
        return []

    @staticmethod
    def start_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        # One-shot: schedule end-of-turn dismiss, then drop this start hook so
        # stale casts cannot keep re-arming and wiping a later Chill Touch.
        entity.register_event_hook('end_of_turn', ChillTouchSpellUndeadEffect, effect=effect)
        _purge_hooks_of_type(entity, 'start_of_turn', effect)
        return []


def _purge_hooks_of_type(holder, event_type, effect):
    if holder is None:
        return
    hooks = getattr(holder, 'entity_event_hooks', None)
    if not hooks or event_type not in hooks:
        return
    hooks[event_type] = [h for h in hooks[event_type] if h.get('effect') is not effect]


class ChillTouchSpell(AttackSpell):
    def build_map(self, orig_action):
        def set_target(target):
            if not target:
                raise ValueError("Invalid target")

            action = orig_action.clone()
            action.target = target
            return action
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies'],
                },
            ],
            'next': set_target,
        }

    def _damage(self, battle, crit=False, opts=None, estimated=False):
        entity = self.source
        level = 1
        if entity.cantrip_level() >= 5:
            level += 1
        if entity.cantrip_level() >= 11:
            level += 1
        if entity.cantrip_level() >= 17:
            level += 1
        return DieRoll.roll(f'{level}d8', crit=crit, battle=battle, entity=entity, description='dice_roll.spells.chill_touch', estimated=estimated)

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts, estimated=True).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = evaluate_spell_attack(self.session, entity, target, self.properties, battle=battle, opts={"action": spell_action})
        result = []
        for event in events:
            result.append(event)

        if hit:
            damage_roll = self._damage(battle, crit=spell_attack_is_critical(attack_roll, entity, target, battle))
            result.extend([{
                'source': entity,
                'target': target,
                'attack_name': "spell.chill_touch",
                'damage_type': self.properties['damage_type'],
                'attack_roll': attack_roll,
                'damage_roll': damage_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'damage': damage_roll,
                'cover_ac': cover_ac_adjustments,
                'type': 'spell_damage',
                'spell': self.properties,
            },
            {
                'source': entity,
                'target': target,
                'type': 'chill_touch',
                'effect': self,
            }])
        else:
            result.extend([{
                'type': 'spell_miss',
                'source': entity,
                'target': target,
                'attack_name': "spell.chill_touch",
                'damage_type': self.properties['damage_type'],
                'attack_roll': attack_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'cover_ac': cover_ac_adjustments,
                'spell': self.properties,
            }])

        return result

    def dismiss(self, entity, _descriptor=None, opts=None):
        # Mirror Ray of Frost: clearing the heal block also drops the caster
        # start_of_turn hook for *this* cast so hooks do not accumulate.
        _purge_hooks(self.source, self)

    @staticmethod
    def heal_override(entity, opt=None):
        return 0

    @staticmethod
    def start_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        target = None
        action = getattr(effect, 'action', None)
        if action is not None:
            target = getattr(action, 'target', None)
        if target is None:
            target = getattr(effect, 'target', None)
        if target is not None:
            target.dismiss_effect(effect)
        else:
            entity.dismiss_effect(effect)
        return []

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'chill_touch':
            return
        source = item['source']
        target = item['target']
        effect = item['effect']
        # Remember the creature for start_of_turn dismiss even if action.target
        # is later mutated.
        effect.target = target

        # A new Chill Touch replaces any prior heal-block from this caster on
        # the same target (duration resets to "until the start of my next turn").
        for entry in list(target.effects.get('heal_override', [])):
            if entry.get('handler') is not ChillTouchSpell:
                continue
            old = entry.get('effect')
            if old is None or old is effect:
                continue
            if getattr(old, 'source', None) is source:
                target.dismiss_effect(old)

        source.add_casted_effect({"target": target, "effect": effect})
        target.register_effect('heal_override', ChillTouchSpell, effect=effect, source=source)
        source.register_event_hook('start_of_turn', ChillTouchSpell, effect=effect)

        if target.undead():
            undead_effect = ChillTouchSpellUndeadEffect(source, target)
            # Replace a prior undead rider from this caster against this target.
            for entry in list(target.effects.get('attack_advantage_modifier', [])):
                if entry.get('handler') is not ChillTouchSpellUndeadEffect:
                    continue
                old = entry.get('effect')
                if old is None or old is undead_effect:
                    continue
                if getattr(old, 'source', None) is source and getattr(old, 'target', None) is target:
                    target.remove_effect(old, {'_allow_id_fallback': False})
                    _purge_hooks(source, old)
            source.register_event_hook('start_of_turn', ChillTouchSpellUndeadEffect, effect=undead_effect)
            target.register_effect(
                'attack_advantage_modifier', ChillTouchSpellUndeadEffect,
                effect=undead_effect, source=source,
            )
