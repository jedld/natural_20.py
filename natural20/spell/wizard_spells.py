from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell
from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.extensions.save_for_half import SaveForHalfMixin
from natural20.utils.spell_attack_util import evaluate_spell_attack


def _spell_dc(entity):
    return entity.spell_save_dc('intelligence')


def _entities_in_squares(battle_map, squares, source):
    targets = []
    for x, y in squares:
        for entity in battle_map.entities_at(x, y):
            if entity is not source and entity not in targets:
                targets.append(entity)
    return targets


class UtilityWizardSpell(Spell):
    """Low-risk tactical representation for utility/narrative wizard spells."""

    TARGET_TYPES = ['self']

    def build_map(self, orig_action):
        target_types = self.properties.get('target_types') or self.TARGET_TYPES
        if target_types == ['point']:
            def set_point(target):
                action = orig_action.clone()
                action.target = target
                return action
            return {'param': [{'type': 'select_square', 'num': 1, 'range': self.properties.get('range', 30)}],
                    'next': set_point}

        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {'param': [{'type': 'select_target', 'num': 1,
                           'range': self.properties.get('range', 5),
                           'target_types': target_types}],
                'next': set_target}

    def resolve(self, entity, battle, spell_action, battle_map):
        return [{
            'type': 'wizard_spell_effect',
            'source': entity,
            'target': spell_action.target or entity,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'wizard_spell_effect':
            return
        if battle and session is None:
            session = battle.session
        target = item.get('target')
        spell = item.get('spell') or {}
        effect = item.get('effect')
        status = spell.get('status') or spell.get('id')
        if target is not None and hasattr(target, 'statuses') and status and status not in target.statuses:
            target.statuses.append(status)
        if target is not None and effect is not None:
            duration = spell.get('duration_seconds')
            target.register_effect(status or 'wizard_spell_effect', UtilityWizardSpell,
                                   effect=effect, source=item.get('source'), duration=duration)
        if session:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': item.get('source'),
                'target': target,
            })


class ProtectionFromEnergySpell(UtilityWizardSpell):
    TARGET_TYPES = ['allies', 'self']

    @staticmethod
    def resistance_override(entity, opts=None):
        opts = opts or {}
        base = list(opts.get('value') or [])
        effect = opts.get('effect')
        damage_type = getattr(effect, 'chosen_damage_type', None) or getattr(effect, 'properties', {}).get('damage_type')
        if damage_type and damage_type not in base:
            base.append(damage_type)
        return base

    def build_map(self, orig_action):
        choices = [[dt.capitalize(), dt] for dt in ('acid', 'cold', 'fire', 'lightning', 'thunder')]

        def set_damage_type(choice):
            action = orig_action.clone()
            action.spell_action.chosen_damage_type = str(choice).lower()

            def set_target(target):
                next_action = action.clone()
                next_action.target = target
                return next_action

            return {'param': [{'type': 'select_target', 'num': 1,
                               'range': self.properties.get('range', 5),
                               'target_types': ['allies', 'self']}],
                    'next': set_target}

        return {'param': [{'type': 'select_choice', 'choices': choices, 'num': 1}],
                'next': set_damage_type}

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'protection_from_energy':
            return UtilityWizardSpell.apply(battle, item, session)
        if battle and session is None:
            session = battle.session
        target = item.get('target')
        effect = item.get('effect')
        if target is not None:
            target.register_effect('resistance_override', ProtectionFromEnergySpell,
                                   effect=effect, source=item.get('source'),
                                   duration=(item.get('spell') or {}).get('duration_seconds'))
            if 'protection_from_energy' not in target.statuses:
                target.statuses.append('protection_from_energy')
        if session:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': item.get('source'),
                'target': target,
            })

    def resolve(self, entity, battle, spell_action, battle_map):
        return [{
            'type': 'protection_from_energy',
            'source': entity,
            'target': spell_action.target,
            'effect': spell_action.spell_action,
            'spell': self.properties,
        }]


class AreaSaveSpell(DamageScalingMixin, SaveForHalfMixin, Spell):
    SHAPE = 'radius'
    SAVE = 'dexterity'
    BASE_DAMAGE = '1d6'
    PER_SLOT_DAMAGE = '1d6'
    BASE_LEVEL = 1
    DAMAGE_TYPE = None
    RANGE_KEY = 'range'
    SIZE_KEY = 'radius'

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        selector = {
            'radius': 'select_radius',
            'line': 'select_line',
            'cone': 'select_cone',
            'square': 'select_square',
        }.get(self.SHAPE, 'select_radius')
        param = {'type': selector, 'num': 1, 'range': self.properties.get(self.RANGE_KEY, 60)}
        if self.SHAPE == 'radius':
            param['radius'] = self.properties.get(self.SIZE_KEY, 20)
        elif self.SHAPE == 'line':
            param['width'] = self.properties.get('width', 5)
        elif self.SHAPE == 'cone':
            param['range'] = self.properties.get('range_cone', self.properties.get('range', 60))
        return {'param': [param], 'next': set_target}

    def _damage(self, battle, opts=None):
        return self._scaled_damage_roll(
            battle, self.BASE_DAMAGE, self.PER_SLOT_DAMAGE,
            opts=opts, base_level=self.BASE_LEVEL,
            description=f"dice_roll.spells.{self.properties.get('id', self.name)}")

    def _target_entities(self, entity, battle_map, target):
        if self.SHAPE == 'line':
            squares = battle_map.squares_in_line(
                battle_map.position_of(entity), target,
                self.properties.get('length', self.properties.get('range', 60)),
                width_ft=self.properties.get('width', 5),
                require_los=self.properties.get('require_los', False))
        elif self.SHAPE == 'cone':
            squares = battle_map.squares_in_cone(
                battle_map.position_of(entity), target,
                self.properties.get('range_cone', self.properties.get('range', 60)) // battle_map.feet_per_grid,
                require_los=self.properties.get('require_los', False))
        elif self.SHAPE == 'square':
            x, y = int(target[0]), int(target[1])
            size = max(1, self.properties.get('area_size', 10) // battle_map.feet_per_grid)
            squares = [(x + dx, y + dy) for dx in range(size) for dy in range(size)]
        else:
            squares = battle_map.squares_in_radius(
                (int(target[0]), int(target[1])),
                self.properties.get(self.SIZE_KEY, 20),
                require_los=self.properties.get('require_los', False))
        return _entities_in_squares(battle_map, squares, entity)

    def resolve(self, entity, battle, spell_action, battle_map):
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', self.BASE_LEVEL)
        targets = self._target_entities(entity, battle_map, spell_action.target)
        return self.resolve_save_for_half(
            targets,
            ability=self.SAVE,
            dc=_spell_dc(entity),
            damage_roll=lambda _t: self._damage(battle, opts={'at_level': at_level}),
            attack_name=self.properties.get('id', str(self)),
            damage_type=self.DAMAGE_TYPE or self.properties.get('damage_type'),
            battle=battle,
        )


class FireballSpell(AreaSaveSpell):
    BASE_DAMAGE = '8d6'
    BASE_LEVEL = 3
    SHAPE = 'radius'


class LightningBoltSpell(AreaSaveSpell):
    BASE_DAMAGE = '8d6'
    BASE_LEVEL = 3
    SHAPE = 'line'


class AganazzarsScorcherSpell(AreaSaveSpell):
    BASE_DAMAGE = '3d8'
    PER_SLOT_DAMAGE = '1d8'
    BASE_LEVEL = 2
    SHAPE = 'line'


class ConeOfColdSpell(AreaSaveSpell):
    BASE_DAMAGE = '8d8'
    PER_SLOT_DAMAGE = '1d8'
    BASE_LEVEL = 5
    SHAPE = 'cone'
    SAVE = 'constitution'


class CloudkillSpell(AreaSaveSpell):
    BASE_DAMAGE = '5d8'
    PER_SLOT_DAMAGE = '1d8'
    BASE_LEVEL = 5
    SHAPE = 'radius'
    SAVE = 'constitution'


class SunburstSpell(AreaSaveSpell):
    BASE_DAMAGE = '12d6'
    PER_SLOT_DAMAGE = '0d6'
    BASE_LEVEL = 8
    SHAPE = 'radius'
    SAVE = 'constitution'


class SunbeamSpell(AreaSaveSpell):
    BASE_DAMAGE = '6d8'
    PER_SLOT_DAMAGE = '0d8'
    BASE_LEVEL = 6
    SHAPE = 'line'
    SAVE = 'constitution'


class StinkingCloudSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']


class WallOfForceSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']


class ScorchingRaySpell(AttackSpell):
    def build_map(self, orig_action):
        cast_level = orig_action.at_level or self.properties.get('level', 2)
        rays = 3 + max(0, cast_level - 2)

        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {'param': [{'type': 'select_target', 'num': rays,
                           'range': self.properties.get('range', 120),
                           'allow_retarget': True,
                           'target_types': ['enemies']}],
                'next': set_target}

    def resolve(self, entity, battle, spell_action, battle_map):
        targets = spell_action.target if isinstance(spell_action.target, list) else [spell_action.target]
        events = []
        for target in targets:
            hit, attack_roll, advantage_mod, cover_ac, adv_info, hook_events = evaluate_spell_attack(
                self.session, entity, target, self.properties, battle=battle, opts={'action': spell_action})
            events.extend(hook_events)
            if hit:
                damage_roll = DieRoll.roll('2d6', crit=attack_roll.nat_20(), battle=battle, entity=entity,
                                           description='dice_roll.spells.scorching_ray')
                events.append({'source': entity, 'target': target, 'attack_name': 'scorching_ray',
                               'damage_type': self.properties.get('damage_type'), 'attack_roll': attack_roll,
                               'damage_roll': damage_roll, 'advantage_mod': advantage_mod, 'adv_info': adv_info,
                               'damage': damage_roll, 'cover_ac': cover_ac, 'type': 'spell_damage',
                               'spell': self.properties})
            else:
                events.append({'source': entity, 'target': target, 'attack_name': 'scorching_ray',
                               'damage_type': self.properties.get('damage_type'), 'attack_roll': attack_roll,
                               'advantage_mod': advantage_mod, 'adv_info': adv_info, 'cover_ac': cover_ac,
                               'type': 'spell_miss', 'spell': self.properties})
        return events


class MelfsAcidArrowSpell(ScorchingRaySpell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        return {'param': [{'type': 'select_target', 'num': 1,
                           'range': self.properties.get('range', 90),
                           'target_types': ['enemies']}],
                'next': set_target}

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        hit, attack_roll, advantage_mod, cover_ac, adv_info, hook_events = evaluate_spell_attack(
            self.session, entity, target, self.properties, battle=battle, opts={'action': spell_action})
        damage_roll = DieRoll.roll('4d4', crit=bool(hit and attack_roll.nat_20()), battle=battle, entity=entity,
                                   description='dice_roll.spells.melfs_acid_arrow')
        damage = damage_roll if hit else damage_roll.half()
        return hook_events + [{'source': entity, 'target': target, 'attack_name': 'melfs_acid_arrow',
                               'damage_type': 'acid', 'attack_roll': attack_roll, 'damage_roll': damage_roll,
                               'advantage_mod': advantage_mod, 'adv_info': adv_info, 'damage': damage,
                               'cover_ac': cover_ac, 'type': 'spell_damage' if damage.result() > 0 else 'spell_miss',
                               'spell': self.properties}]


class ChainLightningSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        return {'param': [{'type': 'select_target', 'num': 4,
                           'range': self.properties.get('range', 150),
                           'allow_retarget': False,
                           'target_types': ['enemies']}],
                'next': set_target}

    def resolve(self, entity, battle, spell_action, battle_map):
        targets = spell_action.target if isinstance(spell_action.target, list) else [spell_action.target]
        damage_roll = DieRoll.roll('10d8', battle=battle, entity=entity,
                                   description='dice_roll.spells.chain_lightning')
        spell = AreaSaveSpell(self.session, entity, self.name, self.properties)
        return spell.resolve_save_for_half(targets, ability='dexterity', dc=_spell_dc(entity),
                                           damage_roll=damage_roll, attack_name='chain_lightning',
                                           damage_type='lightning', battle=battle)


class DisintegrateSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        return {'param': [{'type': 'select_target', 'num': 1,
                           'range': self.properties.get('range', 60),
                           'target_types': ['enemies']}],
                'next': set_target}

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        save = SaveCheck.make(target, 'dexterity', _spell_dc(entity), battle, {'is_magical': True})
        if save.passed:
            return [{'source': entity, 'target': target, 'attack_name': 'disintegrate',
                     'damage_type': 'force', 'type': 'spell_miss', 'spell_save': save.roll,
                     'dc': _spell_dc(entity), 'spell': self.properties}]
        damage_roll = DieRoll.roll('10d6+40', battle=battle, entity=entity,
                                   description='dice_roll.spells.disintegrate')
        return [{'source': entity, 'target': target, 'attack_name': 'disintegrate',
                 'damage_type': 'force', 'damage_roll': damage_roll, 'damage': damage_roll,
                 'spell_save': save.roll, 'save_failed': True, 'dc': _spell_dc(entity),
                 'type': 'spell_damage', 'spell': self.properties}]


class CounterspellSpell(UtilityWizardSpell):
    TARGET_TYPES = ['enemies']

    def _abjuration_check(self, entity, battle, dc):
        bonus = entity.int_mod()
        if entity.class_feature('improved_abjuration'):
            bonus += entity.proficiency_bonus()
        sign = '+' if bonus >= 0 else ''
        return DieRoll.roll(f"1d20{sign}{bonus}", battle=battle, entity=entity,
                            description=f"dice_roll.spells.{self.properties.get('id', self.name)}")

    def resolve(self, entity, battle, spell_action, battle_map):
        target_spell_level = int((getattr(spell_action, 'opts', {}) or {}).get('target_spell_level', 3) or 3)
        cast_level = int(getattr(spell_action, 'at_level', self.properties.get('level', 3)) or 3)
        dc = 10 + target_spell_level
        check = None
        success = cast_level >= target_spell_level
        if not success:
            check = self._abjuration_check(entity, battle, dc)
            success = check.result() >= dc
        return [{
            'type': 'abjuration_check',
            'source': entity,
            'target': spell_action.target,
            'spell': self.properties,
            'roll': check,
            'dc': dc,
            'success': success,
            'cast_level': cast_level,
            'target_spell_level': target_spell_level,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'abjuration_check':
            return
        if battle and session is None:
            session = battle.session
        if session:
            session.event_manager.received_event({
                'event': 'ability_check',
                'ability': 'intelligence',
                'roll': item.get('roll'),
                'dc': item.get('dc'),
                'success': item.get('success'),
                'source': item.get('source'),
                'target': item.get('target'),
            })


class DispelMagicSpell(CounterspellSpell):
    TARGET_TYPES = ['enemies', 'allies']


class BanishmentSpell(CounterspellSpell):
    pass


class MazeSpell(CounterspellSpell):
    pass


class BigbysHandSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']


class OtilukesResilientSphereSpell(CounterspellSpell):
    TARGET_TYPES = ['enemies', 'allies', 'self']


class DetectMagicSpell(UtilityWizardSpell):
    pass


class LeomundsTinyHutSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']


class KnockSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']


class MirrorImageSpell(UtilityWizardSpell):
    pass


class ComprehendLanguagesSpell(UtilityWizardSpell):
    pass


class PrestidigitationSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']


class FeatherFallSpell(UtilityWizardSpell):
    TARGET_TYPES = ['allies', 'self']


class FlySpell(UtilityWizardSpell):
    TARGET_TYPES = ['allies', 'self']


class GustOfWindSpell(AreaSaveSpell):
    BASE_DAMAGE = '0d6'
    PER_SLOT_DAMAGE = '0d6'
    BASE_LEVEL = 2
    SHAPE = 'line'
    SAVE = 'strength'


class AnimateDeadSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']


class TeleportSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']


class MessageSpell(UtilityWizardSpell):
    TARGET_TYPES = ['allies']


class MinorIllusionSpell(UtilityWizardSpell):
    TARGET_TYPES = ['point']
