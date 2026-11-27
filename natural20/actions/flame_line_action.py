"""Line of Flame — the action granted by Investiture of Flame.

Create a line of fire 15 feet long and 5 feet wide from you in a chosen
direction. Each creature in the line makes a Dexterity saving throw or takes
4d8 fire damage (half on a success). The clicked square only fixes the
direction; the line starts at the caster.
"""
from __future__ import annotations

from natural20.action import Action
from natural20.die_roll import DieRoll
from natural20.utils.class_feature_registry import register_class_feature


class FlameLineAction(Action):

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    def clone(self):
        action = FlameLineAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        return action

    def name(self):
        return 'Line of Flame'

    def label(self):
        return 'Line of Flame'

    @staticmethod
    def can(entity, battle, options=None):
        return bool(entity.has_effect('investiture_of_flame'))

    def _spell_dc(self, battle):
        effect = None
        for descriptor in (getattr(self.source, 'effects', {})
                           .get('investiture_of_flame') or []):
            effect = descriptor.get('effect')
            break
        props = getattr(effect, 'spell_properties', None) or {}
        try:
            caster = self.source
            prof = int(caster.proficiency_bonus() or 0)
            key = props.get('spellcasting_ability') or 'wisdom'
            short = {'wisdom': 'wis', 'intelligence': 'int',
                     'charisma': 'cha'}.get(key, 'wis')
            return 8 + prof + int(caster.ability_mod(short) or 0)
        except Exception:
            return 13

    def build_map(self, action):
        def set_target(target):
            new_action = action.clone()
            new_action.target = target
            return new_action

        return {
            'action': self,
            'param': [{'type': 'select_empty_space', 'num': 1, 'range': 15,
                       'require_los': False}],
            'next': set_target,
        }

    def resolve(self, session, map=None, opts=None):
        battle = (opts or {}).get('battle')
        battle_map = battle.map_for(self.source) if battle is not None else map
        if battle_map is None or self.target is None:
            self.result = []
            return self
        origin = tuple(battle_map.position_of(self.source))
        target = self.target
        if hasattr(target, 'entity_uid'):
            target = battle_map.position_of(target)
        if not isinstance(target, (list, tuple)) or len(target) < 2:
            self.result = []
            return self
        direction = (int(target[0]), int(target[1]))
        squares = battle_map.squares_in_line(origin, direction, 15, 5,
                                             require_los=False)
        dc = self._spell_dc(battle)
        from natural20.spell.extensions.save_check import SaveCheck
        spell_props = {'name': 'Investiture of Flame', 'id': 'investiture_of_flame'}
        results = [{'type': 'flame_line_used', 'source': self.source,
                    'target': list(origin), 'battle': battle}]
        roll = DieRoll.roll('4d8', battle=battle, entity=self.source,
                            description='dice_roll.spells.investiture_of_flame_line')
        for x, y in squares:
            for creature in battle_map.entities_at(x, y):
                if creature is self.source or creature.dead():
                    continue
                if battle is not None and not battle.opposing(self.source, creature):
                    continue
                if any(r.get('target') is creature for r in results):
                    continue
                if not hasattr(creature, 'save_throw'):
                    continue
                save = SaveCheck.make(creature, 'dexterity', dc, battle=battle,
                                      opts={'is_magical': True,
                                            'save_tags': ['investiture_of_flame']})
                damage = roll.half() if save.passed else roll
                results.append({
                    'type': 'flame_line_damage',
                    'source': self.source,
                    'target': creature,
                    'attack_name': 'Investiture of Flame',
                    'damage_type': 'fire',
                    'attack_roll': None,
                    'damage_roll': damage,
                    'damage': damage,
                    'advantage_mod': None,
                    'adv_info': None,
                    'spell_save': save.roll,
                    'dc': dc,
                    'spell': spell_props,
                    'battle': battle,
                })
        self.result = results
        return self

    @staticmethod
    def apply(battle, item, session=None):
        item_type = item.get('type')
        if item_type not in ('flame_line_used', 'flame_line_damage'):
            return None
        source = item['source']
        if item_type == 'flame_line_used':
            if battle is not None:
                battle.consume(source, 'action')
            if session is not None:
                session.event_manager.received_event({
                    'event': 'investiture_flame_line', 'source': source,
                    'target': item.get('target'),
                })
            return source
        from natural20.utils.attack_util import damage_event
        damage_event({k: v for k, v in item.items() if k != 'battle'}, battle)
        return item.get('target')


register_class_feature(
    feature_id='investiture_flame_line',
    action_class=FlameLineAction,
    provides=lambda entity: entity.has_effect('investiture_of_flame'),
    builder=lambda session, entity, feature_id: [FlameLineAction(session, entity, feature_id)],
)
