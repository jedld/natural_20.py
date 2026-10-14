"""Free teleport right after an attack (Summon Fiend's yugoloth Claws).

An NPC attack with ``teleport_after_attack: <feet>`` opens a window when it
hits or misses::

    - name: claws
      type: melee_attack
      teleport_after_attack: 30   # to an unoccupied space the creature can see

``PostAttackTeleportAction`` (action type ``post_attack_teleport``) then
moves the creature for free. The window stays open until it is used, the
creature attacks again (the next attack opens a fresh one), or its next turn
starts.
"""

from __future__ import annotations

from natural20.action import Action

WINDOW_KEY = 'post_attack_teleport'


def window_item(attack_action, battle):
    """Result item opening the window for ``attack_action``, or None."""
    npc_action = getattr(attack_action, 'npc_action', None)
    if battle is None or not isinstance(npc_action, dict):
        return None
    try:
        feet = int(npc_action.get('teleport_after_attack') or 0)
    except (TypeError, ValueError):
        feet = 0
    if feet <= 0:
        return None
    return {'type': 'post_attack_teleport_window', 'source': attack_action.source, 'range': feet,
            'attack_name': npc_action.get('label') or npc_action.get('name')}


def window_feet(entity, battle):
    if battle is None:
        return 0
    state = battle.entity_state_for(entity)
    return int((state or {}).get(WINDOW_KEY) or 0)


def _attacks_left(entity, battle):
    from natural20.actions.attack_action import AttackAction
    for spec in getattr(entity, 'npc_actions', None) or []:
        if isinstance(spec, dict) and spec.get('type') in ('melee_attack', 'ranged_attack') \
                and AttackAction.can(entity, battle, {'npc_action': spec}):
            return True
    return False


class PostAttackTeleportAction(Action):
    def __init__(self, session, source, action_type='post_attack_teleport', opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = (opts or {}).get('target')
        self.range = int((opts or {}).get('range') or 30)

    def label(self):
        return 'Teleport'

    def button_label(self):
        return 'Teleport'

    def button_image(self):
        return 'clouds_jaunt'

    def __repr__(self):
        return f"PostAttackTeleport({self.target})"

    @staticmethod
    def can(entity, battle, options=None):
        return window_feet(entity, battle) > 0

    def build_map(self):
        def set_target(target):
            action = self.clone()
            action.target = target
            return action

        return {'action': self, 'param': [{
            'type': 'select_empty_space', 'num': 1, 'require_los': True,
            'range': self.range,
        }], 'next': set_target}

    def clone(self):
        return PostAttackTeleportAction(self.session, self.source, self.action_type,
                                        {'target': self.target, 'range': self.range})

    # --- AI -------------------------------------------------------------------

    def ai_value(self, battle):
        """Close in on a foe while attacks remain; slip away once they're spent if badly hurt."""
        battle_map = battle.map_for(self.source) if battle is not None else None
        if battle_map is None or not isinstance(self.target, (list, tuple)):
            return -1.0
        foes = [e for e in battle.opponents_of(self.source)
                if e.conscious() and battle_map.position_of(e) is not None]
        if not foes:
            return -1.0

        def foes_adjacent(pos):
            return sum(1 for f in foes if battle_map.distance(self.source, f, entity_1_pos=pos) <= 1)

        here = tuple(battle_map.position_of(self.source))
        there = (int(self.target[0]), int(self.target[1]))
        now_adjacent, then_adjacent = foes_adjacent(here), foes_adjacent(there)
        if _attacks_left(self.source, battle):
            return 1.0 if now_adjacent == 0 and then_adjacent > 0 else -1.0
        hurt = self.source.hp() < self.source.max_hp() / 2
        if hurt and now_adjacent > 0 and then_adjacent == 0:
            return 1.0
        return -1.0

    @classmethod
    def options_for(cls, session, entity, battle, map=None, auto_target=True, limit=3):
        if not cls.can(entity, battle):
            return []
        if not auto_target or battle is None:
            return [cls(session, entity, opts={'range': window_feet(entity, battle)})]
        battle_map = map or battle.map_for(entity)
        if battle_map is None:
            return []
        feet = window_feet(entity, battle)
        reach = feet // battle_map.feet_per_grid
        cx, cy = battle_map.position_of(entity)
        scored = []
        for x in range(max(0, cx - reach), min(battle_map.size[0] - 1, cx + reach) + 1):
            for y in range(max(0, cy - reach), min(battle_map.size[1] - 1, cy + reach) + 1):
                if (x, y) == (cx, cy) or not battle_map.placeable(entity, x, y, battle, squeeze=False):
                    continue
                if not battle_map.can_see_square(entity, (x, y)):
                    continue
                action = cls(session, entity, opts={'target': [x, y], 'range': feet})
                value = action.ai_value(battle)
                if value > 0:
                    scored.append((value, action))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [action for _, action in scored[:limit]]

    # --- resolution -------------------------------------------------------------

    def resolve(self, session, map_, opts=None):
        battle = (opts or {}).get('battle')
        target = self.target
        self.result = []
        if map_ is None or not isinstance(target, (list, tuple)) or len(target) != 2:
            return self
        tx, ty = int(target[0]), int(target[1])
        feet = window_feet(self.source, battle) or 30
        cx, cy = map_.position_of(self.source)
        if max(abs(tx - cx), abs(ty - cy)) * map_.feet_per_grid > feet \
                or not map_.placeable(self.source, tx, ty, battle, squeeze=False):
            return self
        self.result = [{'type': 'post_attack_teleport', 'source': self.source, 'map': map_,
                        'target': [tx, ty], 'from': list(map_.position_of(self.source)),
                        'battle': battle, 'refresh_map': True}]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        item_type = item.get('type')
        if item_type == 'post_attack_teleport_window':
            state = battle.entity_state_for(item['source']) if battle is not None else None
            if state is not None:
                state[WINDOW_KEY] = int(item.get('range') or 0)
            return item['source']
        if item_type != 'post_attack_teleport':
            return None
        source = item['source']
        session = session or (battle.session if battle is not None else source.session)
        state = battle.entity_state_for(source) if battle is not None else None
        if state is not None:
            state[WINDOW_KEY] = 0
        battle_map = item['map']
        tx, ty = item['target']
        if battle_map.placeable(source, tx, ty, battle):
            battle_map.move_to(source, tx, ty, battle)
        session.event_manager.received_event({
            'event': 'misty_step', 'source': source, 'position': [tx, ty], 'from': item.get('from'),
        })
        return source
