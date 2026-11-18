from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack, spell_attack_is_critical
from natural20.utils.ac_utils import effective_ac
from natural20.spell.extensions.hit_computations import AttackSpell
import pdb

class RayOfFrostSpell(AttackSpell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
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
        return DieRoll.roll(f'{level}d8', crit=crit, battle=battle, entity=entity, description=self.t('dice_roll.spells.ray_of_frost'), estimated=estimated)

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
            result.extend([
                {
                    'source': entity,
                    'target': target,
                    'attack_name': 'ray_of_frost',
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': attack_roll,
                    'damage_roll': damage_roll,
                    'advantage_mod': advantage_mod,
                    'adv_info': adv_info,
                    'damage': damage_roll,
                    'cover_ac': cover_ac_adjustments,
                    'type': 'spell_damage',
                    'spell': self.properties
                },
                {
                    'source': entity,
                    'target': target,
                    'type': 'ray_of_frost',
                    'effect': self
                }
            ])
        else:
            result.extend([
                {
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': 'ray_of_frost',
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': attack_roll,
                    'advantage_mod': advantage_mod,
                    'adv_info': adv_info,
                    'cover_ac': cover_ac_adjustments,
                    'spell': self.properties
                }
            ])

        return result

    def dismiss(self, entity, _descriptor=None, opts=None):
        # When this cast's slow ends, also unregister its start_of_turn hook
        # from the caster; otherwise the hook fires forever and hooks
        # accumulate one per cast.
        source = self.source
        hooks = getattr(source, 'entity_event_hooks', None)
        if source is not None and hooks:
            for event_type, entries in list(hooks.items()):
                kept = [h for h in entries if h.get('effect') is not self]
                if len(kept) != len(entries):
                    source.entity_event_hooks[event_type] = kept

    @staticmethod
    def start_of_turn(entity, opt=None):
        if not opt:
            opt = {}
        opt['effect'].action.target.dismiss_effect(opt['effect'])

    @staticmethod
    def speed_override(entity, opt=None):
        if opt is None:
            opt = {}
        return max(opt['value'] - 10, 0)

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'ray_of_frost':
            target = item['target']
            source = item['source']
            new_effect = item['effect']
            # The slow does not stack: clear any existing Ray of Frost slow
            # on the target (including its caster-side hook) before
            # registering this cast.
            for entry in list(target.effects.get('speed_override', [])):
                if entry.get('handler') is not RayOfFrostSpell:
                    continue
                old_effect = entry.get('effect')
                if old_effect is None or old_effect is new_effect:
                    continue
                try:
                    target.remove_effect(old_effect)
                except Exception:
                    pass
            source.add_casted_effect({ "target" : target, "effect" : new_effect})
            target.register_effect('speed_override', RayOfFrostSpell, effect=new_effect, source=source)
            source.register_event_hook('start_of_turn', RayOfFrostSpell, effect=new_effect)
