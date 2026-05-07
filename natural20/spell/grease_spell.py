from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.objects.grease_surface import GreaseSurface


class GreaseZone(PersistentAoEZone):
    __slots__ = ("source", "dc", "_tile_objects", "_square_set")

    def __init__(self, source, battle, battle_map, squares, spell):
        super().__init__(
            owner=None,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='grease',
            shape='square',
            duration_rounds=10,
            concentration=False,
            spell=spell,
        )
        self.source = source
        self.dc = source.spell_save_dc()
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}

    def contains(self, pos):
        return tuple(pos) in self._square_set

    def apply_save(self, entity, reason='zone'):
        if entity is None or entity.dead():
            return

        roll = entity.save_throw('dexterity', self.battle, {'is_magical': True})
        success = roll.result() >= self.dc
        became_prone = False

        if not success and not entity.prone():
            entity.do_prone()
            became_prone = True

        self.source.session.event_manager.received_event({
            'event': 'grease_save',
            'source': self.source,
            'target': entity,
            'roll': roll,
            'dc': self.dc,
            'save_type': 'dexterity',
            'success': success,
            'reason': reason,
            'became_prone': became_prone,
        })

    def on_turn_end(self, entity):
        self.apply_save(entity, reason='turn_end')

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


class GreaseSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_square',
                'num': 1,
                'range': self.properties.get('range', 60),
                'size': self.properties.get('area_size', 10),
            }],
            'next': set_target,
        }

    def _target_squares(self, center):
        x, y = int(center[0]), int(center[1])
        return [
            (x, y),
            (x + 1, y),
            (x, y + 1),
            (x + 1, y + 1),
        ]

    def resolve(self, entity, battle, spell_action, battle_map):
        squares = [
            (sx, sy)
            for sx, sy in self._target_squares(spell_action.target)
            if 0 <= sx < battle_map.size[0] and 0 <= sy < battle_map.size[1]
        ]
        return [{
            'type': 'grease',
            'source': entity,
            'target': list(spell_action.target),
            'squares': [list(s) for s in squares],
            'effect': self,
            'spell': self.properties,
            'map': battle_map,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'grease':
            return

        if battle and session is None:
            session = battle.session

        source = item['source']
        battle_map = item.get('map') or battle.map_for(source)
        squares = [tuple(s) for s in item.get('squares', [])]

        zone = GreaseZone(source, battle, battle_map, squares, item.get('effect'))
        for pos in squares:
            tile = GreaseSurface(session, battle_map, source, zone)
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)

        battle.register_zone(zone)

        affected = set()
        for x, y in squares:
            for target in battle_map.entities_at(x, y):
                if target.entity_uid in affected:
                    continue
                affected.add(target.entity_uid)
                zone.apply_save(target, reason='cast')

        session.event_manager.received_event({
            'event': 'grease',
            'source': source,
            'target': item.get('target'),
            'squares': item.get('squares', []),
        })
