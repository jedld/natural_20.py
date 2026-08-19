"""Post-battle combat recaps for PC journals and NPC memories."""

from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

from natural20.npc_memory_store import NpcMemoryStore
from webapp.battle_combat_recap import (
    apply_recap_snapshot,
    battle_had_combat_round,
    build_recap_snapshot,
    load_combat_recap_config,
    parse_llm_recap,
    process_battle_combat_recap,
    snapshot_battle_start,
    summarize_subject,
)


class _FakePC:
    def __init__(self, uid, name='Hero'):
        self.entity_uid = uid
        self.name = name
        self.dialog = False
        self.journal = []
        self.conversation_buffer = []
        self.group = 'a'

    def npc(self):
        return False

    def label(self):
        return self.name

    def dead(self):
        return False

    def unconscious(self):
        return False

    def conscious(self):
        return True

    def hp(self):
        return 12

    def max_hp(self):
        return 12

    def add_journal_entry(self, text, kind='note', title=None, source=None,
                          map_name=None, tags=None, timestamp=None, read=None,
                          seed_id=None):
        entry = {
            'text': text,
            'kind': kind,
            'title': title,
            'source': source,
            'map_name': map_name,
            'tags': list(tags or []),
            'seed_id': seed_id,
            'read': bool(read),
        }
        self.journal.append(entry)
        return entry


class _FakeNPC:
    def __init__(self, uid, name='Villager', *, dialog=True, dead=False):
        self.entity_uid = uid
        self.name = name
        self.dialog = dialog
        self.conversation_buffer = []
        self.group = 'a'
        self._dead = dead

    def npc(self):
        return True

    def label(self):
        return self.name

    def dead(self):
        return self._dead

    def unconscious(self):
        return False

    def conscious(self):
        return not self._dead

    def hp(self):
        return 0 if self._dead else 8

    def max_hp(self):
        return 8


class _FakeMap:
    def __init__(self, name='tavern', entities=None, annotations=None):
        self.name = name
        self.entities = {ent: (2, 3) for ent in (entities or [])}
        self.properties = {'map_annotations': annotations or []}

    def position_of(self, entity):
        return self.entities[entity]

    def map_annotations(self):
        return list(self.properties.get('map_annotations') or [])


class _FakeBattle:
    def __init__(self, combat_order, battle_map, *, round_count=1, turn_index=0, log=None):
        self.combat_order = list(combat_order)
        self.maps = [battle_map]
        self.round = round_count
        self.current_turn_index = turn_index
        self.battle_log = list(log or [])
        self.entities = {
            entity: {'group': getattr(entity, 'group', 'a')}
            for entity in combat_order
        }

    def map_for(self, entity):
        return self.maps[0]

    def tpk(self):
        return False

    def battle_ends(self):
        return True

    def has_player_combatants(self):
        return True


class _FakeGame:
    def __init__(self, battle, entities, *, memory_root=None):
        self._battle = battle
        self._entities = {ent.entity_uid: ent for ent in entities}
        self.maps = {battle.maps[0].name: battle.maps[0]}
        self.output_logger = SimpleNamespace(logging_queue=deque())
        self.npc_memory_store = NpcMemoryStore(memory_root) if memory_root else None
        self.saved = False

    def get_current_battle(self):
        return self._battle

    def get_current_battle_map(self):
        return self._battle.maps[0]

    def get_entity_by_uid(self, uid):
        return self._entities.get(uid)

    def get_map_for_entity(self, entity):
        return self._battle.maps[0]

    def save_game_async(self):
        self.saved = True


def _annotation():
    return {
        'id': 'taproom',
        'label': 'Taproom',
        'kind': 'area',
        'bounds': {'x1': 0, 'y1': 0, 'x2': 10, 'y2': 10},
        'description': 'The crowded taproom of the Blood of the Vine.',
    }


def test_battle_had_combat_round_requires_action_or_turn():
    empty = SimpleNamespace(round=0, current_turn_index=0, battle_log=[])
    assert battle_had_combat_round(empty) is False
    assert battle_had_combat_round(SimpleNamespace(round=1, current_turn_index=0, battle_log=[])) is True
    assert battle_had_combat_round(SimpleNamespace(round=0, current_turn_index=2, battle_log=[])) is True
    assert battle_had_combat_round(SimpleNamespace(round=0, current_turn_index=0, battle_log=['hit'])) is True
    assert battle_had_combat_round(None) is False


def test_load_combat_recap_config_can_disable():
    session = SimpleNamespace(game_properties={'battle_combat_recap': {'enabled': False}})
    assert load_combat_recap_config(session)['enabled'] is False
    assert load_combat_recap_config(SimpleNamespace(game_properties={}))['enabled'] is True


def test_parse_llm_recap_extracts_title_and_summary():
    fallback = {'title': 'Fallback', 'summary': 'fallback', 'body': 'fallback body'}
    parsed = parse_llm_recap(
        "TITLE: Street ambush\nSUMMARY: We cut down the wolves.\nI still smell blood on the road.",
        fallback,
    )
    assert parsed['title'] == 'Street ambush'
    assert parsed['summary'] == 'We cut down the wolves.'
    assert 'smell blood' in parsed['body']


def test_heuristic_recap_mentions_when_where_death_and_talk(tmp_path):
    pc = _FakePC('gomerin', 'Gomerin')
    npc = _FakeNPC('ismark', 'Ismark')
    wolf = _FakeNPC('wolf_1', 'Wolf', dialog=False, dead=True)
    wolf.group = 'b'
    battle_map = _FakeMap('old_svalich_road', [pc, npc, wolf], [_annotation()])
    battle = _FakeBattle([pc, npc, wolf], battle_map, round_count=1, log=['bite'])
    game = _FakeGame(battle, [pc, npc, wolf], memory_root=str(tmp_path))
    game.output_logger.logging_queue.append({'message': '2026:08:17.06:00:00: Wolf died.'})
    session = SimpleNamespace(game_time=12, game_properties={})
    snapshot_battle_start(game, session, battle)
    npc.conversation_buffer.append({'source': pc, 'message': 'Hold the road!', 'time': 12})
    snapshot = build_recap_snapshot(game, session, battle)
    assert snapshot is not None
    ismark = next(item for item in snapshot['subjects'] if item['uid'] == 'ismark')
    recap = summarize_subject(ismark, snapshot, llm_handler=None)
    blob = f"{recap['title']} {recap['summary']} {recap['body']}".lower()
    assert 'taproom' in blob or 'old_svalich_road' in blob or 'svalich' in blob
    assert 'wolf' in blob and 'died' in blob
    assert 'hold the road' in blob


def test_apply_recap_writes_journal_and_memory(tmp_path):
    pc = _FakePC('gomerin', 'Gomerin')
    npc = _FakeNPC('ismark', 'Ismark')
    snapshot = {
        'outcome': 'victory',
        'round_count': 2,
        'game_time': 36,
        'when': {
            'clock_label': '10:00 AM',
            'description': 'Current world time: 10:00 AM (day 1 of the campaign).',
        },
        'location': {
            'map_name': 'old_svalich_road',
            'annotation_labels': ['Old Svalich Road'],
            'description': 'on old_svalich_road',
        },
        'combatants': [
            {'uid': 'gomerin', 'name': 'Gomerin', 'status': 'standing', 'is_player': True},
            {'uid': 'wolf_1', 'name': 'Wolf', 'status': 'dead', 'is_player': False},
        ],
        'subjects': [
            {
                'uid': 'gomerin',
                'name': 'Gomerin',
                'is_player': True,
                'dialog': False,
                'status': 'standing',
                'was_combatant': True,
                'location': {
                    'map_name': 'old_svalich_road',
                    'annotation_labels': ['Old Svalich Road'],
                    'description': 'on old_svalich_road',
                },
                'logs': ['Gomerin hits Wolf for 8 damage.', 'Wolf died.'],
                'conversation_beats': ['Ismark: Stay together!'],
                'major_events': ['Wolf (NPC) died.', '1 conversation beat(s) occurred during the fight.'],
            },
            {
                'uid': 'ismark',
                'name': 'Ismark',
                'is_player': False,
                'dialog': True,
                'status': 'standing',
                'was_combatant': True,
                'location': {
                    'map_name': 'old_svalich_road',
                    'annotation_labels': ['Old Svalich Road'],
                    'description': 'on old_svalich_road',
                },
                'logs': ['Wolf died.'],
                'conversation_beats': ['Ismark: Stay together!'],
                'major_events': ['Wolf (NPC) died.'],
            },
        ],
    }
    game = _FakeGame(
        _FakeBattle([pc, npc], _FakeMap('old_svalich_road', [pc, npc])),
        [pc, npc],
        memory_root=str(tmp_path),
    )
    llm = MagicMock()
    llm.send_message.return_value = (
        "TITLE: Roadside victory\n"
        "SUMMARY: We dropped the wolf on the old road.\n"
        "I heard Ismark shout to stay together as the beast died."
    )
    stats = apply_recap_snapshot(game, snapshot, llm_handler=llm)
    assert stats['players'] == 1
    assert stats['npcs'] == 1
    assert pc.journal[0]['kind'] == 'combat'
    assert pc.journal[0]['title'] == 'Roadside victory'
    assert 'Stay together' in pc.journal[0]['text'] or 'stay together' in pc.journal[0]['text'].lower()
    assert 'died' in pc.journal[0]['text'].lower() or 'wolf' in pc.journal[0]['text'].lower()
    memories = game.npc_memory_store.list_summaries('ismark')
    assert memories
    assert memories[0]['source'] == 'battle_recap'
    assert game.saved is True
    assert llm.send_message.called
    messages, ctx = llm.send_message.call_args[0]
    assert ctx['response_mode'] == 'conversation'
    prompt = messages[1]['content'].lower()
    assert 'old svalich' in prompt or 'old_svalich' in prompt
    assert 'wolf' in prompt and 'died' in prompt
    assert 'stay together' in prompt


def test_process_skips_when_no_combat_round(tmp_path):
    pc = _FakePC('gomerin')
    battle_map = _FakeMap('tavern', [pc])
    battle = _FakeBattle([pc], battle_map, round_count=0, turn_index=0, log=[])
    game = _FakeGame(battle, [pc], memory_root=str(tmp_path))
    session = SimpleNamespace(game_time=0, game_properties={})
    assert process_battle_combat_recap(game, session, background=False) is False
    assert pc.journal == []


def test_process_skips_when_disabled(tmp_path):
    pc = _FakePC('gomerin')
    battle_map = _FakeMap('tavern', [pc])
    battle = _FakeBattle([pc], battle_map, round_count=2, log=['hit'])
    game = _FakeGame(battle, [pc], memory_root=str(tmp_path))
    session = SimpleNamespace(game_time=6, game_properties={'battle_combat_recap': {'enabled': False}})
    assert process_battle_combat_recap(game, session, background=False) is False


def test_snapshot_ignores_pre_battle_conversation(tmp_path):
    pc = _FakePC('gomerin', 'Gomerin')
    npc = _FakeNPC('ismark', 'Ismark')
    pc.conversation_buffer.append({'source': npc, 'message': 'Old gossip', 'time': 1})
    battle_map = _FakeMap('tavern', [pc, npc], [_annotation()])
    battle = _FakeBattle([pc, npc], battle_map, round_count=1, log=['hit'])
    game = _FakeGame(battle, [pc, npc], memory_root=str(tmp_path))
    session = SimpleNamespace(game_time=20, game_properties={})
    snapshot_battle_start(game, session, battle)
    pc.conversation_buffer.append({'source': npc, 'message': 'Look out!', 'time': 20})
    snapshot = build_recap_snapshot(game, session, battle)
    gomerin = next(item for item in snapshot['subjects'] if item['uid'] == 'gomerin')
    assert any('Look out' in line for line in gomerin['conversation_beats'])
    assert not any('Old gossip' in line for line in gomerin['conversation_beats'])
