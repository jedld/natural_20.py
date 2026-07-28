"""Pickpocket action – D&D 5e (2014) Sleight of Hand theft from a creature.

Rules summary (PHB 2014):
- Pickpocket uses Sleight of Hand (DEX-based skill check).
- The target must be within 5 feet (adjacent on the map grid).
- The check is contested by the target's passive Insight.
- On success: the pickpocket steals one small item from the target.
- On failure: the target is aware of the attempt and the pickpocket fails.
- Requires an Action (or Bonus Action for classes like Rogue that grant it).

Campaign settings:
- ``index.json`` key ``pickpocket.enabled`` – global toggle (default ``true``).
- ``index.json`` key ``pickpocket.allow_pc_to_pc`` – when ``false``, PC-to-PC
  pickpocket is blocked entirely.
"""

from __future__ import annotations

import json
import os

from natural20.action import Action
from natural20.utils.pickpocket_items import (
    item_display_name,
    pickpocketable_inventory_items,
    resolve_inventory_item_name,
)


def _pickpocket_pc_to_pc_allowed(session) -> bool:
    """Check if PC-to-PC pickpocket is allowed in the current campaign.

    Returns True by default for backwards compatibility.  The campaign
    ``index.json`` key ``pickpocket.allow_pc_to_pc`` can set this to
    ``false`` to disable PC-vs-PC theft entirely.
    """
    if session is None:
        return True

    # Try to load campaign config from session
    campaign_root = getattr(session, 'root_path', None)
    if campaign_root:
        index_path = os.path.join(campaign_root, 'index.json')
        if os.path.exists(index_path):
            try:
                with open(index_path) as f:
                    cfg = json.load(f)
                pickpocket_cfg = cfg.get('pickpocket', {})
                if isinstance(pickpocket_cfg, dict):
                    if 'allow_pc_to_pc' in pickpocket_cfg:
                        return bool(pickpocket_cfg['allow_pc_to_pc'])
                    if 'pickpocket_allow_pc_to_pc' in cfg:
                        return bool(cfg['pickpocket_allow_pc_to_pc'])
                    return True
                # Backwards compat: top-level boolean
                if pickpocket_cfg in (False, None):
                    return False
                return bool(cfg.get('pickpocket_allow_pc_to_pc', True))
            except Exception:
                pass

    return True


def _is_pc(entity) -> bool:
    """Check if an entity is a Player Character."""
    if entity is None:
        return False
    if hasattr(entity, 'is_npc'):
        try:
            if callable(entity.is_npc):
                return not entity.is_npc()
            return not entity.is_npc
        except Exception:
            pass
    from natural20.player_character import PlayerCharacter
    return isinstance(entity, PlayerCharacter)


class PickpocketAction(Action):
    """A Sleight of Hand check to steal a small item from an adjacent creature."""

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts or {})
        self.target = None
        self.item_name = None
        self.pickpocket_attempt = None
        self.as_bonus_action = False

    @staticmethod
    def can(entity, battle, options=None):
        """A pickpocket attempt requires at least one action (or bonus action).

        Also checks campaign settings to block PC-to-PC pickpocket when
        ``pickpocket.allow_pc_to_pc`` is ``false`` in the campaign index.json.
        """
        if battle is None:
            # Out of combat — check settings via session if available
            if options and options.get('check_settings', True):
                session = getattr(entity, 'session', None)
                if not _pickpocket_pc_to_pc_allowed(session):
                    if _is_pc(entity):
                        # Check if target is a PC (we don't have it here, so allow and check later)
                        pass
            return True
        if options and options.get('bonus'):
            return bool(battle and entity.total_bonus_actions(battle) > 0)
        # Check PC-to-PC restriction when in battle
        if _is_pc(entity) and battle:
            if not _pickpocket_pc_to_pc_allowed(entity.session):
                return False
        return battle is None or entity.total_actions(battle) > 0

    def validate(self, battle_map, target=None):
        """Validate the pickpocket target and item name."""
        errors = []
        if target is None:
            target = self.target
        if target is None:
            errors.append("target is required for pickpocket")
        attempt = self.pickpocket_attempt or {}
        if attempt and not attempt.get('success'):
            return errors
        if not self.item_name:
            errors.append("item_name is required for pickpocket")
        return errors

    def __str__(self):
        return "Pickpocket"

    def clone(self):
        action = PickpocketAction(self.session, self.source, self.action_type)
        action.target = self.target
        action.item_name = self.item_name
        action.pickpocket_attempt = (
            dict(self.pickpocket_attempt) if isinstance(self.pickpocket_attempt, dict)
            else self.pickpocket_attempt
        )
        action.as_bonus_action = self.as_bonus_action
        return action

    @staticmethod
    def serialize_attempt(attempt):
        """Serialize a pickpocket attempt for client round-trips between steps."""
        if not attempt:
            return None
        roll = attempt.get('roll')
        payload = {
            'success': bool(attempt.get('success')),
            'passive_insight': attempt.get('passive_insight'),
            'reason': attempt.get('reason'),
            'message': attempt.get('message'),
        }
        if roll is not None:
            try:
                payload['roll_total'] = int(roll.result())
            except Exception:
                payload['roll_total'] = attempt.get('roll_total')
            try:
                payload['roll_breakdown'] = str(roll)
            except Exception:
                payload['roll_breakdown'] = attempt.get('roll_breakdown')
        else:
            payload['roll_total'] = attempt.get('roll_total')
            payload['roll_breakdown'] = attempt.get('roll_breakdown')
        return payload

    @classmethod
    def deserialize_attempt(cls, payload):
        """Restore attempt metadata echoed from the client between HTTP steps."""
        if not payload or not isinstance(payload, dict):
            return None
        return {
            'success': bool(payload.get('success')),
            'passive_insight': payload.get('passive_insight'),
            'reason': payload.get('reason'),
            'message': payload.get('message'),
            'roll_total': payload.get('roll_total'),
            'roll_breakdown': payload.get('roll_breakdown'),
            'roll': None,
        }

    def roll_pickpocket_attempt(self, session, battle_map, battle=None):
        """Resolve Sleight of Hand vs passive Insight before an item is chosen."""
        target = self.target
        if target is None:
            raise Exception("target is required for pickpocket")

        if _is_pc(self.source) and _is_pc(target):
            if not _pickpocket_pc_to_pc_allowed(session):
                return {
                    'success': False,
                    'reason': 'pc_to_pc_disabled',
                    'message': (
                        "Pickpocketing other player characters is disabled in this campaign."
                    ),
                    'passive_insight': None,
                    'roll': None,
                }

        if battle_map is not None:
            source_pos = None
            target_pos = None
            try:
                source_pos = battle_map.position_of(self.source)
            except (ValueError, KeyError, TypeError):
                source_pos = battle_map.entity_or_object_pos(self.source)
            try:
                target_pos = battle_map.position_of(target)
            except (ValueError, KeyError, TypeError):
                target_pos = battle_map.entity_or_object_pos(target)
            if source_pos and target_pos:
                dx = abs(source_pos[0] - target_pos[0])
                dy = abs(source_pos[1] - target_pos[1])
                if max(dx, dy) > 1:
                    return {
                        'success': False,
                        'reason': 'target_out_of_range',
                        'message': (
                            f"Target {target.name} is too far away for pickpocket "
                            f"(must be within 5 feet)."
                        ),
                        'passive_insight': None,
                        'roll': None,
                    }

        target_incapacitated = target.incapacitated()
        passive_insight = 10 if target_incapacitated else target.passive_insight()
        sleight_of_hand_roll = self.source.sleight_of_hand_check(battle)
        roll_total = sleight_of_hand_roll.result()
        success = roll_total >= passive_insight

        if success:
            message = (
                f"{self.source.name}'s sleight of hand succeeds against "
                f"{target.name} (Sleight of Hand {roll_total} vs passive Insight "
                f"{passive_insight})."
            )
        else:
            message = (
                f"{self.source.name}'s pickpocket attempt on {target.name} fails — "
                f"Sleight of Hand {roll_total} vs passive Insight {passive_insight}."
            )

        return {
            'success': success,
            'roll': sleight_of_hand_roll,
            'roll_total': roll_total,
            'passive_insight': passive_insight,
            'reason': None if success else 'detection',
            'message': message,
        }

    def build_map(self):
        """Build the targeting map for pickpocket.

        Returns a UI config that asks for:
        1. An adjacent creature target (5 ft).
        2. A Sleight of Hand attempt (rolled server-side).
        3. On success, one small stealable item from the target's inventory.
        """
        def after_attempt(attempt):
            finished = self.clone()
            finished.target = attempt.get('_target') or finished.target
            finished.pickpocket_attempt = attempt
            if not attempt.get('success'):
                return finished

            target_uid = getattr(finished.target, 'entity_uid', None)

            def done(item_name):
                resolved = finished.clone()
                resolved.item_name = item_name
                return resolved

            return {
                "action": finished,
                "param": [
                    {
                        "type": "select_pickpocket_item",
                        "label": "Item lifted",
                        "target_uid": target_uid,
                    }
                ],
                "next": done,
            }

        def set_target_then_attempt(target):
            action_with_target = self.clone()
            action_with_target.target = target
            target_uid = getattr(target, 'entity_uid', None)

            def bridge_attempt(attempt):
                attempt['_target'] = target
                return after_attempt(attempt)

            return {
                "action": action_with_target,
                "param": [
                    {
                        "type": "pickpocket_attempt",
                        "label": "Attempt pickpocket",
                        "target_uid": target_uid,
                    }
                ],
                "next": bridge_attempt,
            }

        return {
            "action": self,
            "param": [
                {
                    "type": "select_target",
                    "range": 5,
                    "target_types": ["creatures"],
                    "num": 1,
                }
            ],
            "next": set_target_then_attempt,
        }

    @staticmethod
    def build(session, source):
        """Build a pickpocket action map."""
        action = PickpocketAction(session, source, 'pickpocket')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        """Resolve the pickpocket attempt.

        D&D 5e 2014: Sleight of Hand vs passive Insight is rolled in the
        pickpocket_attempt step before the thief chooses a lifted item.
        """
        if opts is None:
            opts = {}

        battle = opts.get('battle')
        target = opts.get("target") or self.target

        if target is None:
            raise Exception("target is required for pickpocket")

        attempt = self.pickpocket_attempt
        if attempt is None and opts.get('pickpocket_attempt'):
            attempt = self.deserialize_attempt(opts.get('pickpocket_attempt'))
            self.pickpocket_attempt = attempt

        if attempt and not attempt.get('success'):
            self.result = [{
                'source': self.source,
                'target': target,
                'type': 'pickpocket',
                'success': False,
                'item_name': self.item_name,
                'battle': battle,
                'roll': attempt.get('roll'),
                'roll_total': attempt.get('roll_total'),
                'roll_breakdown': attempt.get('roll_breakdown'),
                'passive_insight': attempt.get('passive_insight'),
                'reason': attempt.get('reason') or 'detection',
                'message': attempt.get('message') or (
                    f"{self.source.name}'s pickpocket attempt on {target.name} fails."
                ),
            }]
            return self

        if not attempt or not attempt.get('success'):
            raise Exception("pickpocket_attempt is required for pickpocket")

        if not self.item_name:
            raise Exception("item_name is required for pickpocket")

        resolved_item = resolve_inventory_item_name(session, target, self.item_name)
        if resolved_item is None:
            self.result = [{
                'source': self.source,
                'target': target,
                'type': 'pickpocket',
                'success': False,
                'item_name': self.item_name,
                'battle': battle,
                'reason': 'item_not_found',
                'message': (
                    f"{target.name} does not have a stealable item matching "
                    f"'{self.item_name}'."
                ),
            }]
            return self

        stealable = {
            row['name']
            for row in pickpocketable_inventory_items(session, target)
        }
        if resolved_item not in stealable:
            self.result = [{
                'source': self.source,
                'target': target,
                'type': 'pickpocket',
                'success': False,
                'item_name': self.item_name,
                'battle': battle,
                'reason': 'item_not_stealable',
                'message': (
                    f"'{self.item_name}' is too large or not available to pickpocket "
                    f"from {target.name}."
                ),
            }]
            return self

        self.item_name = resolved_item

        sleight_of_hand_roll = attempt.get('roll')
        passive_insight = attempt.get('passive_insight')
        item_label = item_display_name(session, self.item_name)
        roll_total = attempt.get('roll_total')
        if roll_total is None and sleight_of_hand_roll is not None:
            try:
                roll_total = sleight_of_hand_roll.result()
            except Exception:
                roll_total = None

        self.result = [{
            'source': self.source,
            'target': target,
            'type': 'pickpocket',
            'success': True,
            'item_name': self.item_name,
            'battle': battle,
            'roll': sleight_of_hand_roll,
            'roll_total': roll_total,
            'roll_breakdown': attempt.get('roll_breakdown'),
            'passive_insight': passive_insight,
            'message': (
                f"{self.source.name} successfully pickpockets {item_label} from "
                f"{target.name} (Sleight of Hand {roll_total} vs passive Insight "
                f"{passive_insight})."
            ),
        }]

        return self

    @staticmethod
    def apply(battle, item, session=None):
        """Apply the pickpocket result."""
        if item['type'] != 'pickpocket':
            return

        event_manager = battle.event_manager if battle else (session.event_manager if session else None)
        source = item['source']
        target = item['target']
        item_name = item.get('item_name', 'unknown item')
        item_label = item_display_name(session, item_name)
        event_payload = {
            'source': source,
            'target': target,
            'roll': item.get('roll'),
            'roll_total': item.get('roll_total'),
            'roll_breakdown': item.get('roll_breakdown'),
            'passive_insight': item.get('passive_insight'),
            'item_name': item_name,
            'item_label': item_label,
            'reason': item.get('reason'),
            'message': item.get('message'),
        }

        if item['success']:
            stolen = False
            if hasattr(target, 'remove_item') and hasattr(source, 'add_item'):
                if getattr(target, 'inventory', None) and item_name in target.inventory:
                    if target.inventory[item_name].get('qty', 0) > 0:
                        removed_item = target.deduct_item(item_name, 1)
                        if removed_item:
                            source.add_item(item_name, 1, source_item=removed_item)
                            stolen = True

            if event_manager:
                event_manager.received_event({
                    **event_payload,
                    'success': True,
                    'stolen': stolen,
                    'event': 'pickpocket',
                })
        else:
            if event_manager:
                event_manager.received_event({
                    **event_payload,
                    'success': False,
                    'event': 'pickpocket_failed',
                })

        # Consume action economy
        if battle:
            if item.get('bonus_action'):
                battle.consume(source, 'bonus_action')
            else:
                battle.consume(source, 'action')


class PickpocketBonusAction(PickpocketAction):
    """Pickpocket as a bonus action (Rogue feature: Thief's Fast Hands)."""

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    @staticmethod
    def can(entity, battle):
        if not battle or entity.total_bonus_actions(battle) <= 0:
            return False
        # Only certain classes can pickpocket as bonus action
        if entity.class_feature('thief_fast_hands'):
            return True
        return False
