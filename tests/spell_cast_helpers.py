"""Shared setup for SRD spell tests: a wizard and a cleric versus an ogre."""
import random

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
import natural20.die_roll as die_roll_module
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class _StickyFudge(dict):
    """Fudge table whose entries survive every roll (``DieRoll.fudge`` is single-use)."""

    def pop(self, key, *default):
        if key in self:
            return self[key]
        return default[0] if default else None


class sticky_d20:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self._saved = die_roll_module.FUDGE_HASH
        die_roll_module.FUDGE_HASH = _StickyFudge({20: self.value})
        return self

    def __exit__(self, *exc):
        die_roll_module.FUDGE_HASH = self._saved
        return False


class SpellArena:
    def __init__(self, seed=3, with_battle=True, map_name='battle_sim_objects'):
        random.seed(seed)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = self.session.register_map(map_name, Map(self.session, map_name))
        self.battle = Battle(self.session, self.map) if with_battle else None
        self.wizard = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.ogre = self.session.npc('ogre')
        if self.battle is not None:
            self.battle.add(self.wizard, 'heroes', position=[0, 5])
            self.battle.add(self.cleric, 'heroes', position=[0, 6])
            self.battle.add(self.ogre, 'foes', position=[4, 5])
            self.battle.start(combat_order=[self.wizard, self.cleric, self.ogre])
            for e in (self.wizard, self.cleric, self.ogre):
                e.reset_turn(self.battle)
        else:
            self.map.add(self.wizard, 0, 5)
            self.map.add(self.cleric, 0, 6)
            self.map.add(self.ogre, 4, 5)

    def learn(self, caster, spell, level):
        klass = 'wizard' if caster is self.wizard else 'cleric'
        caster.properties.setdefault('prepared_spells', []).append(spell)
        if klass == 'wizard':
            caster.properties.setdefault('spellbook', []).append(spell)
        if level > 0:
            caster.spell_slots.setdefault(klass, {})[level] = 4

    def build(self, caster, spell, level, *targets):
        step = SpellAction.build(self.session, caster)['next']([spell, level])
        queue = list(targets)
        while isinstance(step, dict):
            step = step['next'](queue.pop(0))
        return step

    def cast(self, caster, spell, level, *targets, d20=None, opts=None):
        if self.battle is not None:
            caster.reset_turn(self.battle)
        action = self.build(caster, spell, level, *targets)
        if opts:
            action.opts = {**(action.opts or {}), **opts}
        if d20 is None:
            self._run(action)
        else:
            with sticky_d20(d20):
                self._run(action)
        return action

    def _run(self, action):
        action.resolve(self.session, self.map, {'battle': self.battle})
        if self.battle is not None:
            self.battle.commit(action)
        else:
            for item in action.result:
                SpellAction.apply(None, item, self.session)

    def end_turn(self, entity):
        entity.resolve_trigger('end_of_turn', {'battle': self.battle})
        if self.battle is not None:
            self.battle.trigger_event('end_of_turn', self.battle, {'target': entity})

    def start_turn(self, entity):
        entity.reset_turn(self.battle)
