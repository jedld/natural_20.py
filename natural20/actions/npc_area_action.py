"""NPC area abilities from YAML (breath weapons and similar saves).

An NPC ``actions`` entry with ``type: area_save``::

    - name: noxious_breath
      label: Noxious Breath
      type: area_save
      shape: cone              # cone | line | radius (sphere around the creature)
      range: 15                # cone/line length or radius, in feet
      width: 5                 # line width
      save: constitution
      dc: 14
      damage_die: 6d6
      damage_type: poison
      half_on_success: true    # default
      recharge: 5-6            # rolled at the start of the creature's turns once used
      cost: action             # action (default) | bonus_action
      on_fail: [exhaustion:1]  # also condition:<name> (until the end of the target's next turn)
      success_immunity:        # a successful save makes the creature immune for a while
        key: draconian_noxious_breath
        hours: 24

Used abilities are listed in ``attributes['recharge_spent']``;
``roll_recharges`` (called from ``Battle.start_turn``) rolls a d6 for each.
"""

from __future__ import annotations

from natural20.action import Action
from natural20.die_roll import DieRoll

ACTION_TYPE = 'npc_area_ability'
SPENT_KEY = 'recharge_spent'
IMMUNITY_KEY = 'ability_immunities'


def area_configs(entity):
    props = getattr(entity, 'properties', None) or {}
    return [a for a in props.get('actions') or []
            if isinstance(a, dict) and a.get('type') == 'area_save' and a.get('name')]


def area_config(entity, name):
    return next((a for a in area_configs(entity) if a.get('name') == name), None)


def _spent(entity):
    attrs = getattr(entity, 'attributes', None)
    if not isinstance(attrs, dict):
        return []
    return attrs.setdefault(SPENT_KEY, [])


def is_ready(entity, config):
    return config is not None and config.get('name') not in _spent(entity)


def recharge_min(config):
    raw = str((config or {}).get('recharge') or '').strip()
    if not raw:
        return None
    try:
        return int(raw.split('-')[0])
    except ValueError:
        return None


def roll_recharges(entity, battle=None):
    """Roll a d6 for each spent ability; on ``recharge`` or higher it's ready again."""
    spent = _spent(entity)
    for name in list(spent):
        config = area_config(entity, name)
        needed = recharge_min(config)
        if needed is None:
            continue
        roll = DieRoll.roll('1d6', entity=entity, battle=battle, description='dice_roll.recharge')
        recharged = roll.result() >= needed
        if recharged:
            spent.remove(name)
        session = getattr(entity, 'session', None)
        if session is not None:
            session.event_manager.received_event({
                'event': 'recharge', 'source': entity, 'ability': config.get('label') or name,
                'roll': roll, 'recharged': recharged,
            })


def _cost(config):
    return 'bonus_action' if (config or {}).get('cost') == 'bonus_action' else 'action'


def _has_cost(entity, battle, config):
    if battle is None or battle.entity_state_for(entity) is None:
        return True
    if _cost(config) == 'bonus_action':
        return entity.total_bonus_actions(battle) > 0
    return entity.total_actions(battle) > 0


def immune_until(target, key):
    attrs = getattr(target, 'attributes', None)
    if not isinstance(attrs, dict) or not key:
        return None
    return (attrs.get(IMMUNITY_KEY) or {}).get(key)


def _is_immune(target, key, session):
    until = immune_until(target, key)
    if until is None:
        return False
    now = int(getattr(session, 'game_time', 0) or 0)
    return now < int(until)


class NpcAreaAction(Action):
    """Use one ``area_save`` ability; ``ability`` names the YAML entry."""

    def __init__(self, session, source, action_type=ACTION_TYPE, opts=None):
        super().__init__(session, source, action_type, opts)
        opts = opts or {}
        self.ability = opts.get('ability')
        self.target = opts.get('target')
        self.as_bonus_action = _cost(self._config()) == 'bonus_action'

    def _config(self):
        if self.ability:
            return area_config(self.source, self.ability)
        configs = [c for c in area_configs(self.source) if is_ready(self.source, c)]
        return configs[0] if configs else None

    def label(self):
        config = self._config() or {}
        return config.get('label') or str(config.get('name', 'Area Ability')).replace('_', ' ').title()

    def button_label(self):
        return self.label()

    def button_image(self):
        return 'breath_weapon'

    def describe(self):
        config = self._config() or {}
        shape = config.get('shape', 'cone')
        parts = [self.label(), f"{config.get('range', 15)}-ft {shape}",
                 f"DC {config.get('dc', 10)} {config.get('save', 'dexterity')} save",
                 f"{config.get('damage_die', '')} {config.get('damage_type', '')}".strip()]
        if config.get('recharge'):
            parts.append(f"recharge {config['recharge']}")
        return ', '.join(p for p in parts if p)

    def to_h(self):
        data = super().to_h()
        if self.ability:
            data['choice'] = self.ability
        return data

    def __repr__(self):
        return f"NpcAreaAction({self.ability}->{self.target})"

    @staticmethod
    def can(entity, battle, options=None):
        if not hasattr(entity, 'npc') or not entity.npc():
            return False
        return any(is_ready(entity, c) and _has_cost(entity, battle, c) for c in area_configs(entity))

    @classmethod
    def options_for(cls, session, entity, battle, map=None, auto_target=True):
        actions = []
        for config in area_configs(entity):
            if not is_ready(entity, config) or not _has_cost(entity, battle, config):
                continue
            action = cls(session, entity, ACTION_TYPE, {'ability': config['name']})
            if not auto_target or battle is None:
                actions.append(action)
                continue
            from natural20.utils.action_builder import autobuild
            actions.extend(autobuild(session, cls, entity, battle, map=map,
                                     build_info=action.build_map()))
        return actions

    def _param(self, config):
        shape = config.get('shape', 'cone')
        if shape == 'cone':
            return {'type': 'select_cone', 'range': int(config.get('range', 15)), 'require_los': True}
        if shape == 'line':
            return {'type': 'select_line', 'range': int(config.get('range', 30)),
                    'width': int(config.get('width', 5))}
        return None

    def build_map(self):
        if not self.ability:
            choices = [[c.get('label') or c['name'], c['name']] for c in area_configs(self.source)
                       if is_ready(self.source, c)]

            def set_choice(choice):
                action = self.clone()
                action.ability = choice
                action.as_bonus_action = _cost(action._config()) == 'bonus_action'
                return action.build_map()

            if len(choices) == 1:
                return set_choice(choices[0][1])
            return {'action': self, 'param': [{'type': 'select_choice', 'choices': choices}],
                    'next': set_choice}

        param = self._param(self._config() or {})
        if param is None:
            return self

        def set_target(target):
            action = self.clone()
            action.target = target
            return action

        return {'action': self, 'param': [param], 'next': set_target}

    def clone(self):
        action = NpcAreaAction(self.session, self.source, self.action_type, {'ability': self.ability})
        action.target = self.target
        return action

    def area_squares(self, battle_map):
        config = self._config() or {}
        origin = tuple(battle_map.position_of(self.source))
        shape = config.get('shape', 'cone')
        if shape in ('radius', 'self', 'emanation'):
            return battle_map.squares_in_radius(origin, int(config.get('range', 10)), require_los=True)
        target = self.target
        if hasattr(target, 'entity_uid'):
            target = battle_map.position_of(target)
        if not isinstance(target, (list, tuple)) or len(target) < 2:
            return []
        direction = (int(target[0]), int(target[1]))
        if shape == 'line':
            return battle_map.squares_in_line(origin, direction, int(config.get('range', 30)),
                                              int(config.get('width', 5)), require_los=True)
        range_squares = max(1, int(config.get('range', 15)) // battle_map.feet_per_grid)
        return battle_map.squares_in_cone(origin, direction, range_squares, require_los=True)

    def targets_in_area(self, battle_map):
        found = []
        for x, y in self.area_squares(battle_map):
            for creature in battle_map.entities_at(x, y):
                if creature is self.source or creature in found:
                    continue
                if not hasattr(creature, 'save_throw') or not creature.allow_targeting():
                    continue
                found.append(creature)
        return found

    def ai_value(self, battle, enemy_count=1):
        """Expected damage to foes minus allies caught in the area."""
        if battle is None:
            return 0.0
        battle_map = battle.map_for(self.source)
        if battle_map is None:
            return 0.0
        config = self._config() or {}
        try:
            avg = float(DieRoll.roll(str(config.get('damage_die', '0'))).expected())
        except Exception:
            avg = 0.0
        score = 0.0
        for creature in self.targets_in_area(battle_map):
            weight = -1.0 if battle.allies(self.source, creature) else 1.0
            if weight > 0 and not creature.conscious():
                weight = 0.25
            score += weight * avg * 0.75
        return score

    def resolve(self, session, map_, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        config = self._config()
        if config is None or not is_ready(self.source, config) or map_ is None:
            self.result = []
            return self
        dc = int(config.get('dc', 10))
        save_type = config.get('save', 'dexterity')
        damage_type = config.get('damage_type', 'fire')
        immunity = config.get('success_immunity') or {}
        roll = DieRoll.roll(str(config.get('damage_die', '1d6')), entity=self.source, battle=battle,
                            description=f"dice_roll.{config['name']}")
        results = [{'type': 'npc_area_used', 'source': self.source, 'ability': config['name'],
                    'label': self.label(), 'cost': _cost(config), 'battle': battle}]
        from natural20.spell.extensions.save_check import SaveCheck
        for creature in self.targets_in_area(map_):
            if immunity.get('key') and _is_immune(creature, immunity['key'], session):
                results.append({'type': 'npc_area_immune', 'source': self.source, 'target': creature,
                                'label': self.label()})
                continue
            save = SaveCheck.make(creature, save_type, dc, battle=battle,
                                  opts={'save_tags': [config['name']]})
            if save.passed and config.get('half_on_success', True) is False:
                damage = None
            else:
                damage = roll.half() if save.passed and hasattr(roll, 'half') else roll
            results.append({
                'type': 'npc_area_damage', 'source': self.source, 'target': creature,
                'attack_name': self.label(), 'damage_type': damage_type, 'damage': damage,
                'spell_save': save.roll, 'dc': dc, 'saved': save.passed,
                'on_fail': [] if save.passed else list(config.get('on_fail') or []),
                'immunity': immunity if save.passed else None, 'battle': battle,
            })
        self.result = results
        return self

    @staticmethod
    def apply(battle, item, session=None):
        item_type = item.get('type')
        if item_type not in ('npc_area_used', 'npc_area_damage', 'npc_area_immune'):
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else getattr(source, 'session', None)
        if item_type == 'npc_area_used':
            if battle is not None and battle.entity_state_for(source) is not None:
                battle.consume(source, item.get('cost', 'action'))
            config = area_config(source, item['ability'])
            if recharge_min(config) is not None:
                spent = _spent(source)
                if item['ability'] not in spent:
                    spent.append(item['ability'])
            if session is not None:
                session.event_manager.received_event({
                    'event': 'npc_area_ability', 'source': source, 'ability': item.get('label'),
                })
            return source
        target = item['target']
        if item_type == 'npc_area_immune':
            if session is not None:
                session.event_manager.received_event({
                    'event': 'npc_area_immune', 'source': source, 'target': target,
                    'ability': item.get('label'),
                })
            return target
        if item.get('damage') is not None:
            from natural20.utils.attack_util import damage_event
            damage_event({k: v for k, v in item.items() if k not in ('on_fail', 'immunity', 'saved')},
                         battle)
        if target.dead():
            return target
        for rider in item.get('on_fail') or []:
            kind, _, value = str(rider).partition(':')
            if kind == 'exhaustion':
                target.set_exhaustion_level(target.exhaustion_level() + int(value or 1))
                if session is not None:
                    session.event_manager.received_event({
                        'event': 'exhaustion', 'source': source, 'target': target,
                        'level': target.exhaustion_level(),
                    })
            elif kind == 'condition' and value:
                from natural20.effects.timed_condition_effect import TimedConditionEffect
                TimedConditionEffect.apply_to(target, value, source=source, battle=battle)
        immunity = item.get('immunity')
        if immunity and immunity.get('key') and isinstance(target.attributes, dict):
            now = int(getattr(session, 'game_time', 0) or 0)
            seconds = int(float(immunity.get('hours', 24)) * 3600)
            target.attributes.setdefault(IMMUNITY_KEY, {})[immunity['key']] = now + seconds
        return target
