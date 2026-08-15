from dataclasses import dataclass
from natural20.action import Action
from natural20.item_library.healing_potion import HealingPotion
from natural20.item_library.speak_with_animals_scroll import SpeakWithAnimalsScroll
from natural20.item_library.spell_scroll import SpellScroll
from natural20.item_library.magic_spell_item import MagicSpellItem, PotionEffectItem
import pdb

@dataclass
class UseItemAction(Action):
    def __init__(self, session, source, action_type):
        super().__init__(session, source, action_type)
        self.session = session
        self.source = source
        self.action_type = action_type
        self.target = None
        self.target_item = None
        self.at_level = 0
        self.spell_action = None
        # When True, ``apply`` consumes the source's reaction instead of
        # an action -- used by readied (Hold) actions that fire as the
        # source's reaction (e.g. "ready a healing potion if my ally goes
        # down").
        self.as_reaction = False
        # When set, a consumable is deducted from this container instead of
        # top-level inventory (sheet "use from backpack" convenience).
        self.inventory_container = None


    def __str__(self):
        if self.target_item:
            return f"UseItem: {self.target_item.name}"
        return "UseItem"
    
    def __repr__(self):
        return self.__str__()
    
    def clone(self):
        action = UseItemAction(self.session, self.source, self.action_type)
        action.target = self.target
        action.target_item = self.target_item
        action.at_level = self.at_level
        action.spell_action = self.spell_action
        action.as_reaction = self.as_reaction
        action.inventory_container = getattr(self, 'inventory_container', None)
        return action
    
    @staticmethod
    def can(entity, battle):
        return battle is None or entity.total_actions(battle) > 0

    def can_use_on(self, entity, battle=None):
        return self.target_item.can_use(entity, battle)

    def usable_items(self):
        return self.source.usable_items()

    def charge_badge_text(self):
        """Compact charge label for the Use Item action icon (single charged item only)."""
        charged = []
        for entry in self.usable_items():
            summary = self.source.item_charge_summary(entry['name'])
            if summary is not None:
                charged.append(summary)
        if len(charged) == 1:
            s = charged[0]
            return f"{s['current']}/{s['max']}"
        return None

    @staticmethod
    def build(session, source):
        action = UseItemAction(session, source, "use_item")
        return action.build_map()

    def build_map(self):
        def next_fn(item):
            action = self.clone()
            action.target_item = item
            return action.build_next(item)

        return {
            "action": self,
            "param": [
                {
                    "type": "select_item"
                }
            ],
            "next": next_fn
        }

    @staticmethod
    def build_self_use(session, source, item_name, target=None, container_name=None):
        """Build a UseItemAction that auto-targets ``target`` (default: self).

        Used by the character-sheet inventory. Items that need map targeting
        (scrolls, cones, etc.) raise ``ValueError``.
        """
        action = UseItemAction(session, source, 'use_item')
        action.inventory_container = container_name or None
        step = action.build_next(item_name)
        resolved_target = target or source

        def _finish(step_obj):
            if isinstance(step_obj, UseItemAction):
                if getattr(step_obj, 'target', None) is None:
                    step_obj.target = resolved_target
                step_obj.inventory_container = action.inventory_container
                return step_obj
            if isinstance(step_obj, dict) and isinstance(step_obj.get('action'), UseItemAction):
                inner = step_obj['action']
                if getattr(inner, 'target', None) is None:
                    inner.target = resolved_target
                inner.inventory_container = action.inventory_container
                return inner
            raise ValueError('This item needs to be used from the action bar.')

        if isinstance(step, UseItemAction):
            return _finish(step)
        if not isinstance(step, dict):
            raise ValueError('This item needs to be used from the action bar.')

        params = step.get('param') or []
        if not params:
            return _finish(step)
        param = params[0] if isinstance(params[0], dict) else {}
        param_type = param.get('type')
        next_fn = step.get('next')
        if param_type == 'select_target' and callable(next_fn):
            target_types = [str(entry).strip().lower() for entry in (param.get('target_types') or [])]
            if 'self' not in target_types and 'allies' not in target_types:
                raise ValueError('This item needs a target from the action bar.')
            return _finish(next_fn(resolved_target))
        raise ValueError('This item needs to be used from the action bar.')

    def build_next(self, item):
        item_details = dict(self.session.load_equipment(item) or {})
        if not item_details.get("usable"):
            raise Exception(f"item {item_details.get('name', item)} not usable!")

        inventory_entry = (getattr(self.source, 'inventory', None) or {}).get(item) or {}
        for meta_key in ('room_label', 'room_landmark', 'notify_npc', 'source_entity_uid'):
            if inventory_entry.get(meta_key) is not None:
                item_details[meta_key] = inventory_entry.get(meta_key)

        klass = UseItemAction.to_item_class(item_details['item_class'])
        item_details['name'] = item
        self.target_item = klass(self.session, None, item_details)
        return self.target_item.build_map(self)

    def to_item_class(item_class):
        if item_class == 'HealingPotion':
            klass = HealingPotion
        elif item_class == 'SpellScroll':
            klass = SpellScroll
        elif item_class == 'SpeakWithAnimalsScroll':
            klass = SpeakWithAnimalsScroll
        elif item_class == 'MagicSpellItem':
            klass = MagicSpellItem
        elif item_class == 'PotionEffectItem':
            klass = PotionEffectItem
        elif item_class == 'RoomServiceBuzzerItem':
            from natural20.item_library.room_service_buzzer import RoomServiceBuzzerItem
            klass = RoomServiceBuzzerItem
        else:
            raise Exception(f"item class {item_class} not found")
        return klass


    def resolve(self, session, map=None, opts=None):
        if opts is None:
            opts = {}
        battle = opts.get("battle")
        result_payload = {
            "source": self.source,
            "target": self.target,
            "map": map,
            "battle": battle,
            "type": "use_item",
            "item": self.target_item,
            "as_reaction": bool(getattr(self, 'as_reaction', False)),
            "inventory_container": getattr(self, 'inventory_container', None),
        }
        item_result = self.target_item.resolve(self.source, battle, self, map)

        if isinstance(item_result, dict):
            result_payload.update(item_result)
            self.result = [result_payload]
        else:
            self.result = []
            for item in item_result:
                if (item['type'] == 'use_item'):
                    item.update(result_payload)
                else:
                    item.update({'target_item': self.target_item})
                self.result.append(item)
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item["type"] == "use_item":
            if session is None:
                session = battle.session
            if session:
                session.event_manager.received_event({"event": "use_item", "source": item["source"], "item": item["item"], "target": item["target"]})
            item["item"].use(item["target"], item)
            if item["item"].consumable():
                item["source"].deduct_item(
                    item["item"].name,
                    1,
                    container_name=item.get("inventory_container"),
                )
            if battle:
                if item.get("as_reaction"):
                    # Readied use_item: the action was prepared on the
                    # previous turn and fires as the source's reaction now.
                    try:
                        battle.consume(item["source"], 'reaction')
                    except Exception:
                        # Fallback for unusual entity states.
                        battle.entity_state_for(item["source"])["reaction"] = max(
                            0, battle.entity_state_for(item["source"]).get("reaction", 0) - 1)
                else:
                    battle.entity_state_for(item["source"])["action"] -= 1
