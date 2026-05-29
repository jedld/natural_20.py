"""Action-type resolution utilities extracted from app.py.

Provides ``action_type_to_class()`` and ``resolve_requested_action_type()``
so blueprints don't need to import the entire app module.
"""

from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.dodge_action import DodgeAction
from natural20.actions.disengage_action import DisengageAction, DisengageBonusAction
from natural20.actions.dash import DashAction, DashBonusAction
from natural20.actions.prone_action import ProneAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.stand_action import StandAction
from natural20.actions.attack_action import TwoWeaponAttackAction, LinkedAttackAction
from natural20.actions.action_surge_action import ActionSurgeAction
from natural20.actions.drop_concentration_action import DropConcentrationAction
from natural20.actions.shove_action import ShoveAction
from natural20.actions.hide_action import HideAction, HideBonusAction
from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.grapple_action import GrappleAction, DropGrappleAction
from natural20.actions.escape_grapple_action import EscapeGrappleAction
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.interact_action import InteractAction
from natural20.actions.look_action import LookAction
from natural20.actions.help_action import HelpAction
from natural20.actions.find_familiar_action import FindFamiliarAction
from natural20.actions.summon_familiar_action import SummonFamiliarAction
from natural20.actions.mage_hand_action import MageHandAction
from natural20.actions.lay_on_hands_action import LayOnHandsAction
from natural20.actions.flurry_of_blows_action import FlurryOfBlowsAction
from natural20.actions.patient_defense_action import PatientDefenseAction
from natural20.actions.step_of_the_wind_action import StepOfTheWindAction
from natural20.actions.feline_agility_action import FelineAgilityAction
from natural20.actions.martial_arts_bonus_attack_action import MartialArtsBonusAttackAction
from natural20.actions.bardic_inspiration_action import BardicInspirationAction
from natural20.actions.wild_shape_action import WildShapeAction, RevertWildShapeAction, WildShapeAttackAction
from natural20.actions.rage_action import RageAction, EndRageAction, RecklessAttackAction
from natural20.actions.ready_action import ReadyAction


_ACTION_TYPE_MAP = {
    'SecondWindAction': SecondWindAction,
    'DodgeAction': DodgeAction,
    'DisengageAction': DisengageAction,
    'DisengageBonusAction': DisengageBonusAction,
    'DashAction': DashAction,
    'DashBonusAction': DashBonusAction,
    'ProneAction': ProneAction,
    'SpellAction': SpellAction,
    'StandAction': StandAction,
    'TwoWeaponAttackAction': TwoWeaponAttackAction,
    'ActionSurgeAction': ActionSurgeAction,
    'DropConcentrationAction': DropConcentrationAction,
    'ShoveAction': ShoveAction,
    'HideAction': HideAction,
    'HideBonusAction': HideBonusAction,
    'FirstAidAction': FirstAidAction,
    'GrappleAction': GrappleAction,
    'DropGrappleAction': DropGrappleAction,
    'EscapeGrappleAction': EscapeGrappleAction,
    'UseItemAction': UseItemAction,
    'InteractAction': InteractAction,
    'LookAction': LookAction,
    'LinkedAttackAction': LinkedAttackAction,
    'HelpAction': HelpAction,
    'FindFamiliarAction': FindFamiliarAction,
    'SummonFamiliarAction': SummonFamiliarAction,
    'MageHandAction': MageHandAction,
    'LayOnHandsAction': LayOnHandsAction,
    'FlurryOfBlowsAction': FlurryOfBlowsAction,
    'PatientDefenseAction': PatientDefenseAction,
    'StepOfTheWindAction': StepOfTheWindAction,
    'FelineAgilityAction': FelineAgilityAction,
    'MartialArtsBonusAttackAction': MartialArtsBonusAttackAction,
    'BardicInspirationAction': BardicInspirationAction,
    'WildShapeAction': WildShapeAction,
    'RevertWildShapeAction': RevertWildShapeAction,
    'WildShapeAttackAction': WildShapeAttackAction,
    'RageAction': RageAction,
    'EndRageAction': EndRageAction,
    'RecklessAttackAction': RecklessAttackAction,
    'ReadyAction': ReadyAction,
}


def action_type_to_class(action_type):
    """Map an action type string to its Python class.

    Raises ``ValueError`` for unknown types.
    """
    cls = _ACTION_TYPE_MAP.get(action_type)
    if cls is None:
        raise ValueError(f"Unknown action type {action_type}")
    return cls


def resolve_requested_action_type(entity, session, battle, battle_map, action_class, requested_action_type):
    """Return the concrete action type to use.

    If ``requested_action_type`` is provided it wins.  Otherwise we look
    through the entity's available actions for the first match of
    ``action_class``.
    """
    if requested_action_type:
        return requested_action_type

    try:
        available_actions = entity.available_actions(
            session,
            battle,
            auto_target=False,
            map=battle_map,
        )
        for available_action in available_actions:
            if isinstance(available_action, action_class) and available_action.action_type:
                return available_action.action_type
    except Exception:
        pass

    return None


def validate_targets(action, entity, target, current_map, battle=None):
    if battle:
        valid_targets = battle.valid_targets_for(entity, action)
        if isinstance(target, list):
            for t in target:
                if t not in valid_targets:
                    raise ValueError(f"Invalid target {t} ({current_map.entity_by_uid(t)})")
        else:
            if target not in valid_targets:
                raise ValueError(f"Invalid target {target}")


def process_action_hash(action):
    return action.to_h()
