from __future__ import annotations

from natural20.player_character import PlayerCharacter
from natural20.spell.spell import Spell
from natural20.utils.corpses import animate_remains_into, corpses_at, is_corpse

CORPSE_SIZES = ('small', 'medium')


class AnimateDeadSpell(Spell):
    """Animate Dead (3rd-level necromancy, SRD).

    Raises the Small/Medium humanoid remains in the chosen square (within range)
    as a zombie, or as a skeleton when the remains are bones. Each slot level
    above 3rd animates two more remains within range of the caster. The undead
    join the caster's side with ``owner`` set to the caster. The 1-minute casting
    time keeps it out of combat (see ``SpellAction.can_cast``).
    """

    BASE_LEVEL = 3

    def build_map(self, orig_action):
        def set_point(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_square',
                'num': 1,
                'range': self.properties.get('range', 10),
                'require_corpse': True,
                'require_humanoid': True,
                'corpse_sizes': list(CORPSE_SIZES),
            }],
            'next': set_point,
        }

    @staticmethod
    def _eligible(entity):
        return is_corpse(entity, humanoid=True, sizes=CORPSE_SIZES)

    @staticmethod
    def _point(target):
        if isinstance(target, (list, tuple)) and len(target) == 2 and all(isinstance(v, int) for v in target):
            return tuple(target)
        return None

    def _range_squares(self, battle_map):
        return max(1, int(self.properties.get('range', 10)) // battle_map.feet_per_grid)

    def validate(self, battle_map, target=None):
        self.errors = []
        point = self._point(target if target is not None else self.target)
        if point is None:
            self.errors.append('Select the square of a corpse or pile of bones')
            return False
        source = self.source
        if source is not None and battle_map.distance_to_square(source, *point) > self._range_squares(battle_map):
            self.errors.append('Target is out of range')
        if not corpses_at(battle_map, *point, humanoid=True, sizes=CORPSE_SIZES):
            self.errors.append('No Small or Medium humanoid remains there')
        return len(self.errors) == 0

    def _remains_to_animate(self, entity, battle_map, point, at_level):
        chosen = corpses_at(battle_map, *point, humanoid=True, sizes=CORPSE_SIZES)[:1]
        extra = max(0, (int(at_level or self.BASE_LEVEL) - self.BASE_LEVEL) * 2)
        if extra and entity in battle_map.entities:
            reach = self._range_squares(battle_map)
            nearby = [
                e for e in battle_map.entities
                if e not in chosen and self._eligible(e) and battle_map.distance(entity, e) <= reach
            ]
            nearby.sort(key=lambda e: battle_map.distance(entity, e))
            chosen.extend(nearby[:extra])
        return chosen

    @staticmethod
    def undead_kind(remains):
        props = getattr(remains, 'properties', None) or {}
        if props.get('remains') == 'bones':
            return 'skeleton'
        return 'zombie'

    def resolve(self, entity, battle, spell_action, battle_map):
        point = self._point(spell_action.target)
        remains = self._remains_to_animate(entity, battle_map, point, getattr(spell_action, 'at_level', None)) if point else []
        return [{
            'type': 'animate_dead',
            'source': entity,
            'target': point,
            'map': battle_map,
            'remains': remains,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'animate_dead':
            return None
        if battle and session is None:
            session = battle.session
        caster = item['source']
        battle_map = item['map']
        if session is None or battle_map is None:
            return None

        raised = []
        for remains in item.get('remains') or []:
            if not AnimateDeadSpell._eligible(remains) or remains not in battle_map.entities:
                continue
            position = battle_map.position_of(remains)
            kind = AnimateDeadSpell.undead_kind(remains)
            undead = session.npc(kind, {'name': f"{remains.label()} ({kind.capitalize()})"})
            undead.owner = caster
            undead.properties['summoner_uid'] = caster.entity_uid

            if isinstance(remains, PlayerCharacter):
                # Keep the PC registered (its sheet, inventory, and owner
                # survive); its body returns when the undead is destroyed.
                animate_remains_into(remains, undead, battle_map, battle)
            else:
                if battle is not None and remains in battle.entities:
                    battle.remove(remains)
                battle_map.remove(remains, battle=battle)
            battle_map.place(position, undead)
            undead.group = getattr(caster, 'group', None) or undead.group
            if battle is not None and battle.ongoing() and caster in battle.entities:
                battle.add(undead, battle.entities[caster]['group'], add_to_initiative=True)
            session.register_entity(undead)
            raised.append(undead)

            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': item.get('effect'),
                'source': caster,
                'target': undead,
            })
        item['raised'] = raised
        return None
