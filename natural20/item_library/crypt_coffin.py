"""Crypt coffin that triggers events when specific remains are placed inside."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from natural20.item_library.chest import Chest
from natural20.action import Action


class CryptCoffin(Chest):
    """A coffin that triggers events when specific remains are placed inside.
    
    YAML configuration:
        accepted_items: [rose_remains, thorn_remains]  # item slugs to accept
        on_accept: ghost_peaced                         # event to trigger on placement
        entity_uid: rose_coffin                         # unique identifier
    """

    def __init__(self, session, map, properties=None):
        super().__init__(session, map, properties or {})
        self.accepted_items: List[str] = properties.get('accepted_items', []) or []
        self.on_accept_event: str = properties.get('on_accept', '') or ''
        self.accepted_count: Dict[str, int] = {}
        self._peaced = False

    def add_item(self, item_name: str, qty: int, source_item: Any = None) -> None:
        """Override to detect when accepted remains are placed in the coffin."""
        super().add_item(item_name, qty, source_item)
        
        if item_name in self.accepted_items:
            self.accepted_count[item_name] = self.accepted_count.get(item_name, 0) + qty
            
            if self.accepted_count[item_name] >= 1 and self.on_accept_event and not self._peaced:
                self._peaced = True
                self.resolve_trigger(self.on_accept_event)

    def build_map(self, action, action_object):
        """Build the interaction flow for store (deposit remains into coffin)."""
        # Allow store interaction for depositing items
        if action in ('loot', 'store', 'give'):
            def next_action(items):
                action_object.other_params = items
                return action_object
            return {
                'action': action_object,
                'param': [{
                    'type': 'select_items',
                    'label': 'Place items in coffin',
                    'items': {},  # Empty - items come from PC inventory
                    'mode': 'transfer',
                    'focus': 'deposit',
                    'source_items': action_object.source.inventory if hasattr(action_object, 'source') and hasattr(action_object.source, 'inventory') else {},
                    'target_items': self.inventory or {},
                }],
                'next': next_action
            }
        return action_object

    def available_interactions(self, entity, battle=None, admin=False):
        """Allow store/give interactions to deposit items into the coffin."""
        interactions = super().available_interactions(entity, battle, admin)
        # Always allow store and give for placing items in the coffin
        interactions['store'] = {
            'prompt': 'Place items in coffin'
        }
        interactions['give'] = {
            'prompt': 'Give items to coffin'
        }
        # Allow loot to remove items
        interactions['loot'] = {
            'prompt': 'Take items from coffin'
        }
        return interactions

    def opaque(self, origin=None):
        return False

    def passable(self, origin=None):
        return True
