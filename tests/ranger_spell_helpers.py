"""Shared setup for the ranger / utility spell tests: a level 11 ranger (or
wizard) and goblins on an open 16x16 map in a temporary campaign."""
import json
import random
from contextlib import contextmanager

import yaml

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.npc import Npc
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.serialization import Serialization

SIZE = 16


@contextmanager
def forced_save(entity, total):
    """Every saving throw ``entity`` makes inside the block totals ``total``."""
    entity.save_throw = lambda *args, **kwargs: DieRoll.roll(str(total))
    try:
        yield
    finally:
        del entity.save_throw


def make_campaign(tmp_path, ruleset='5e-2014', packs=()):
    (tmp_path / 'maps').mkdir(exist_ok=True)
    rows = ['.' * SIZE for _ in range(SIZE)]
    (tmp_path / 'maps' / 'field.yml').write_text(yaml.safe_dump({
        'name': 'Field', 'description': 'open field',
        'map': {'illumination': 1.0, 'base': rows, 'meta': rows},
        'legend': {},
    }))
    (tmp_path / 'game.yml').write_text(yaml.safe_dump({
        'name': 'Spell Fixture', 'ruleset': ruleset, 'starting_map': 'maps/field'}))
    (tmp_path / 'index.json').write_text(json.dumps({
        'tile_size': 70, 'title': 't', 'logins': [], 'default_controllers': [],
        'expansion_packs': {p: p for p in packs},
    }))
    return Session(root_path=str(tmp_path), event_manager=EventManager())


def ranger_props(**extra):
    props = {
        'name': 'Ranger', 'entity_uid': 'ranger', 'race': 'human',
        'classes': {'ranger': 11}, 'level': 11,
        'max_hp': 81, 'hp': 81, 'hit_die': 'inherit',
        'ability': {'str': 13, 'dex': 18, 'con': 12, 'int': 8, 'wis': 18, 'cha': 8},
        'saving_throw_proficiencies': ['str', 'dex'],
        'prepared_spells': [],
        'equipped': ['studded_leather', 'longbow', 'arrows', 'shortsword'],
        'inventory': [{'type': 'studded_leather', 'qty': 1}, {'type': 'longbow', 'qty': 1},
                      {'type': 'arrows', 'qty': 20}, {'type': 'shortsword', 'qty': 1}],
        'token': ['R'], 'group': 'a',
    }
    props.update(extra)
    return props


def wizard_props(**extra):
    props = {
        'name': 'Wizard', 'entity_uid': 'wizard', 'race': 'human',
        'classes': {'wizard': 11}, 'level': 11,
        'max_hp': 60, 'hp': 60, 'hit_die': 'inherit',
        'ability': {'str': 8, 'dex': 14, 'con': 12, 'int': 18, 'wis': 12, 'cha': 10},
        'saving_throw_proficiencies': ['int', 'wis'],
        'prepared_spells': [], 'spellbook': [],
        'equipped': ['dagger'], 'inventory': [{'type': 'dagger', 'qty': 1}],
        'token': ['W'], 'group': 'a',
    }
    props.update(extra)
    return props


class Arena:
    """Caster at (2, 2), ally at (3, 2) and goblins at (6, 2) / (7, 2)."""

    def __init__(self, tmp_path, ruleset='5e-2014', packs=(), caster='ranger', with_battle=True, seed=5,
                 spells=(), slot_class=None):
        random.seed(seed)
        self.session = make_campaign(tmp_path, ruleset, packs)
        self.map = Map(self.session, 'maps/field')
        self.session.register_map('field', self.map)
        self.battle = Battle(self.session, self.map) if with_battle else None
        props = ranger_props if caster == 'ranger' else wizard_props
        self.klass = slot_class or caster
        self.caster = PlayerCharacter(self.session, props(prepared_spells=list(spells),
                                                          spellbook=list(spells)))
        self.ally = PlayerCharacter(self.session, ranger_props(name='Ally', entity_uid='ally'))
        self.goblin = Npc(self.session, 'goblin', {'name': 'g1'})
        self.goblin2 = Npc(self.session, 'goblin', {'name': 'g2'})
        placements = [(self.caster, 2, 2, 'a'), (self.ally, 3, 2, 'a'),
                      (self.goblin, 6, 2, 'b'), (self.goblin2, 7, 2, 'b')]
        for entity, x, y, group in placements:
            self.session.register_entity(entity)
            self.map.add(entity, x, y, group)
            if self.battle is not None:
                self.battle.add(entity, group, add_to_initiative=True)
        if self.battle is not None:
            self.battle.start(combat_order=[self.caster, self.ally, self.goblin, self.goblin2])
            for entity, *_ in placements:
                entity.reset_turn(self.battle)
        for level in range(1, 7):
            self.caster.spell_slots.setdefault(self.klass, {})[level] = 3

    def spell(self, slug):
        return self.session.load_spell(slug)

    def build(self, spell, level, *targets, caster=None):
        step = SpellAction.build(self.session, caster or self.caster)['next']([spell, level])
        queue = list(targets)
        while isinstance(step, dict):
            step = step['next'](queue.pop(0))
        return step

    def cast(self, spell, level, *targets, caster=None):
        caster = caster or self.caster
        if self.battle is not None:
            caster.reset_turn(self.battle)
        action = self.build(spell, level, *targets, caster=caster)
        action.resolve(self.session, self.map, {'battle': self.battle})
        if self.battle is not None:
            self.battle.commit(action)
        else:
            for item in action.result:
                SpellAction.apply(None, item, self.session)
        return action

    def round_trip(self):
        dump = Serialization().serialize(self.session, self.battle, {'field': self.map})
        session2, battle2, maps2 = Serialization().deserialize(dump)
        for name, battle_map in (maps2 or {}).items():
            session2.register_map(name, battle_map)
        return session2, battle2, maps2
