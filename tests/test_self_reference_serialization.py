"""Regression tests for saves where an entity is self-linked through its own
effect descriptors (``source``/``target`` pointing back at itself).

The dumper writes such an entity as one node whose subtree aliases itself,
and PyYAML's constructor refuses to build cycles through custom-tagged nodes
("found unconstructable recursive node"). Two layers fix this:

* dump side: ``Entity.to_dict`` stores descriptor entity refs as uid strings;
* load side: ``break_recursive_object_refs`` rewrites legacy back-edges to
  the ancestor's ``entity_uid`` before construction.
"""

import unittest

from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.session import Session
from natural20.utils.serialization import (
    Serialization,
    SafeLoaderWithConstructors,
    break_recursive_object_refs,
)

import yaml


class _CycleNode:
    """Minimal custom-tagged class used to build legacy self-referencing docs."""

    def __init__(self, data):
        self.data = data


def _cycle_constructor(loader, node):
    # Same shape as generic_constructor: deep=True cannot survive a cycle.
    return _CycleNode(loader.construct_mapping(node, deep=True))


_LEGACY_VALUE_CYCLE = """
root:
  - &x !test_cycle
    entity_uid: npc_self_linked
    casted_effects:
    - target: *x
"""

_LEGACY_KEY_CYCLE = """
root:
  ? &x !test_cycle
    entity_uid: npc_self_linked
    effects:
      mirror_image:
      - source: *x
  : [33, 14]
"""


class _RoundTrip(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def test_self_cast_effect_descriptors_round_trip(self):
        session = self.make_session()
        battle_map = Map(session, 'entryway')
        character = battle_map.entity_by_uid('gomerin')

        character.casted_effects.append({
            'effect': None, 'expiration': None,
            'source': character, 'target': character,
        })
        character.effects['test_self_link'] = [{
            'effect': None, 'expiration': None, 'source': character,
        }]

        dump = Serialization().serialize(session, None, {'entryway': battle_map})
        new_session, _battle, new_maps = Serialization().deserialize(dump)
        restored = new_maps['entryway'].entity_by_uid('gomerin')
        self.assertIsNotNone(restored)

        casted = restored.casted_effects[0]
        self.assertIs(casted['target'], restored)
        effects = restored.effects['test_self_link']
        self.assertIs(effects[0]['source'], restored)

    def test_dump_emits_no_self_referencing_node_cycles(self):
        session = self.make_session()
        battle_map = Map(session, 'entryway')
        character = battle_map.entity_by_uid('gomerin')
        character.casted_effects.append({
            'effect': None, 'expiration': None,
            'source': character, 'target': character,
        })
        dump = Serialization().serialize(session, None, {'entryway': battle_map})
        node = yaml.compose_all(dump).__next__()
        self.assertFalse(_node_graph_has_cycle(node))
        break_recursive_object_refs(node)
        self.assertFalse(_node_graph_has_cycle(node))


def _node_graph_has_cycle(node, path=None, seen=None):
    path = path if path is not None else set()
    seen = seen if seen is not None else set()
    if id(node) in path:
        return True
    if id(node) in seen or not isinstance(node, (yaml.MappingNode, yaml.SequenceNode)):
        return False
    path.add(id(node))
    children = ([c for pair in node.value for c in pair]
                if isinstance(node, yaml.MappingNode) else node.value)
    for child in children:
        if _node_graph_has_cycle(child, path, seen):
            return True
    path.discard(id(node))
    seen.add(id(node))
    return False


class _LegacyCycleLoading(unittest.TestCase):
    def setUp(self):
        SafeLoaderWithConstructors.add_constructor('!test_cycle', _cycle_constructor)

    def tearDown(self):
        SafeLoaderWithConstructors.yaml_constructors.pop('!test_cycle', None)

    def _load(self, source):
        return yaml.load(source, Loader=SafeLoaderWithConstructors)

    def test_value_position_back_edge_becomes_uid_string(self):
        doc = self._load(_LEGACY_VALUE_CYCLE)
        node = doc['root'][0]
        self.assertIsInstance(node, _CycleNode)
        self.assertEqual(node.data['entity_uid'], 'npc_self_linked')
        self.assertEqual(node.data['casted_effects'][0]['target'], 'npc_self_linked')

    def test_key_position_back_edge_becomes_uid_string(self):
        doc = self._load(_LEGACY_KEY_CYCLE)
        entries = list(doc['root'].items())
        self.assertEqual(len(entries), 1)
        node, position = entries[0]
        self.assertIsInstance(node, _CycleNode)
        self.assertEqual(position, [33, 14])
        effects = node.data['effects']['mirror_image']
        self.assertEqual(effects[0]['source'], 'npc_self_linked')

    def test_standard_collection_cycles_still_work(self):
        # Plain map cycles are constructible natively; do not rewrite them.
        doc = self._load('a: &x\n  b: *x\n')
        self.assertIs(doc['a']['b'], doc['a'])

    def test_break_helper_rewrites_legacy_cycles(self):
        node = yaml.compose_all(_LEGACY_VALUE_CYCLE).__next__()
        self.assertTrue(_node_graph_has_cycle(node))
        break_recursive_object_refs(node)
        self.assertFalse(_node_graph_has_cycle(node))


if __name__ == '__main__':
    unittest.main()
