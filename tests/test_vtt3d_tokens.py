"""Tests for 3D VTT campaign token models (vtt3d.yml ``tokens:`` section).

Covers the engine side of the HeroForge-style figure pipeline:
catalog loading, key precedence (uid -> type -> name), file resolution
with extension fallback, and the ``entities[].model`` payload emitted
into ``/map_state``."""
from natural20.web.map_state import entities_from_tiles
from natural20.web.vtt3d_catalog import (
    TOKEN_ENTRY_EXTS,
    _norm_token_spec,
    entity_token_keys,
    load_vtt3d_tokens,
    resolve_token_model,
    resolve_token_src,
)


def _stub(uid, name, pid):
    class Stub:
        pass
    s = Stub()
    s.entity_uid = uid
    s.name = name
    s.properties = {'id': pid}
    return s


def test_norm_token_spec_normalizes_src():
    spec = _norm_token_spec({
        'src': '/assets/models/tokens/paladin.glb',
        'height': 7,
        'color': 'gold',
    })
    assert spec == {'src': 'models/tokens/paladin.glb', 'height': 7, 'color': 'gold'}
    assert _norm_token_spec('models/tokens/x.glb') == {'src': 'models/tokens/x.glb'}
    assert _norm_token_spec({'name': 'Paladin'}) == {'label': 'Paladin'}
    assert _norm_token_spec(None) is None


def test_token_entry_exts_prefers_glb():
    assert TOKEN_ENTRY_EXTS[0] == '.glb'
    assert '.stl' in TOKEN_ENTRY_EXTS


def test_entity_token_keys_precedence():
    keys = entity_token_keys(_stub('npc-vampire-1', 'Count Alucard #2', 'vampire'))
    assert keys == ['npc-vampire-1', 'vampire', 'Count Alucard #2', 'Count Alucard']


def test_entity_token_keys_from_dict():
    keys = entity_token_keys({'uid': 'pc-ara', 'name': 'Ara', 'properties': {'id': 'ranger'}})
    assert keys == ['pc-ara', 'ranger', 'Ara']


def test_resolve_token_model_matches_keys():
    tokens = {
        'pc-ara': {'src': 'models/tokens/ara.glb', 'height': 6},
        'vampire': {'src': 'models/tokens/vampire.glb'},
        'Generic Bob': {'src': 'bob.glb'},
    }
    assert resolve_token_model(_stub('pc-ara', 'Ara', 'ranger'), tokens)['src'] == 'models/tokens/ara.glb'
    # uid misses -> type wins over name
    assert resolve_token_model(_stub('npc-9', 'Bob', 'vampire'), tokens)['src'] == 'models/tokens/vampire.glb'
    assert resolve_token_model(_stub('npc-9', 'Generic Bob', 'ghoul'), tokens)['src'] == 'bob.glb'
    assert resolve_token_model(_stub('npc-9', 'Nobody', 'ghoul'), tokens) is None
    # keys match case-insensitively
    assert resolve_token_model(_stub('NPC-9', 'Bob', 'Vampire'), tokens)['src'] == 'models/tokens/vampire.glb'


def test_resolve_token_src_extension_fallback(tmp_path):
    models = tmp_path / 'assets' / 'models' / 'tokens'
    models.mkdir(parents=True)
    (models / 'paladin.stl').write_bytes(b'solid')
    src = resolve_token_src(tmp_path, 'models/tokens/paladin')
    assert src == 'models/tokens/paladin.stl'

    (models / 'paladin.glb').write_bytes(b'glTF')
    assert resolve_token_src(tmp_path, 'models/tokens/paladin') == 'models/tokens/paladin.glb'

    assert resolve_token_src(tmp_path, 'models/tokens/missing') is None
    # path traversal is rejected
    assert resolve_token_src(tmp_path, '../secret.glb') is None


def test_load_vtt3d_tokens_from_campaign_file(tmp_path):
    (tmp_path / 'vtt3d.yml').write_text(
        'tokens:\n'
        '  vampire:\n'
        '    src: /assets/models/tokens/vampire.glb\n'
        '    height: 8\n'
        '    color: "#8888aa"\n'
        '  pc-ara:\n'
        '    src: models/tokens/ara.glb\n'
        '    rotate_y: 90\n',
        encoding='utf-8',
    )

    class FakeSession:
        root_path = str(tmp_path)
        properties = {}

    tokens = load_vtt3d_tokens(FakeSession())
    assert tokens['vampire']['src'] == 'models/tokens/vampire.glb'
    assert tokens['vampire']['height'] == 8
    assert tokens['pc-ara']['rotate_y'] == 90


def test_entities_from_tiles_emits_model(tmp_path):
    models = tmp_path / 'assets' / 'models' / 'tokens'
    models.mkdir(parents=True)
    (models / 'ara.glb').write_bytes(b'glTF')

    ara = _stub('pc-ara', 'Ara', 'ranger')
    wolf = _stub('npc-wolf-1', 'Wolf', 'wolf')

    class FakeSession:
        root_path = str(tmp_path)

        def entity_by_uid(self, uid):
            return {'pc-ara': ara, 'npc-wolf-1': wolf}.get(str(uid))

    class FakeMap:
        session = FakeSession()
        entities = [ara, wolf]

    tokens = {
        'ranger': {'src': 'models/tokens/ara', 'height': 6, 'rotate_y': 180},
        'Ara': {'src': 'models/tokens/ara'},
    }
    tiles = [
        {'entity': {'name': 'Ara'}, 'id': 'pc-ara', 'x': 1, 'y': 2, 'name': 'Ara'},
        {'entity': {'name': 'Wolf'}, 'id': 'npc-wolf-1', 'x': 3, 'y': 4, 'name': 'Wolf'},
        # entity gone from the session -> fall back to tile name match
        {'entity': {'name': 'Ara'}, 'id': 'ghost-1', 'x': 5, 'y': 6, 'name': 'Ara'},
    ]
    out = entities_from_tiles(tiles, battle_map=FakeMap(), tokens=tokens)
    by_uid = {e['uid']: e for e in out}
    assert by_uid['pc-ara']['model'] == {
        'src': 'models/tokens/ara.glb', 'height': 6, 'rotate_y': 180,
    }
    assert 'model' not in by_uid['npc-wolf-1']
    # name fallback still resolves the file
    assert by_uid['ghost-1']['model']['src'] == 'models/tokens/ara.glb'
    # no tokens -> no model keys at all
    plain = entities_from_tiles(tiles, battle_map=FakeMap())
    assert all('model' not in e for e in plain)


# ---------------------------------------------------------------------------
# size-change spells (Enlarge/Reduce, Large Form) scale token models
# ---------------------------------------------------------------------------

def test_model_size_scale_from_size_override():
    from natural20.web.vtt3d_catalog import model_size_scale

    # entity.size() is what size_override effects override (Enlarge: medium -> large)
    enlarged = _stub('pc-ara', 'Ara', 'ranger')
    enlarged.properties['size'] = 'medium'
    enlarged.size = lambda: 'large'
    assert model_size_scale(enlarged) == 2.0

    reduced = _stub('pc-ara', 'Ara', 'ranger')
    reduced.properties['size'] = 'medium'
    reduced.size = lambda: 'small'
    assert model_size_scale(reduced) == 0.5

    natural = _stub('ogre-1', 'Ogre', 'ogre')
    natural.properties['size'] = 'large'
    natural.size = lambda: 'large'
    assert model_size_scale(natural) is None

    # race fallback provides the natural size when properties has none
    race_kid = _stub('hal-1', 'Hal', 'rogue')
    race_kid.race_properties = {'size': 'small'}
    race_kid.size = lambda: 'medium'
    assert model_size_scale(race_kid) == 2.0

    # unknown sizes and missing entities are not comparable
    weird = _stub('x', 'X', 'blob')
    weird.properties['size'] = 'colossal'
    weird.size = lambda: 'large'
    assert model_size_scale(weird) is None
    assert model_size_scale(None) is None


def test_entities_from_tiles_size_scale(tmp_path):
    models = tmp_path / 'assets' / 'models' / 'tokens'
    models.mkdir(parents=True)
    (models / 'ara.glb').write_bytes(b'glTF')

    ara = _stub('pc-ara', 'Ara', 'ranger')
    ara.properties['size'] = 'medium'
    ara.size = lambda: 'large'  # under Enlarge/Reduce
    gob = _stub('npc-gob-1', 'Gob', 'goblin')
    gob.properties['size'] = 'small'
    gob.size = lambda: 'small'  # natural

    class FakeSession:
        root_path = str(tmp_path)

        def entity_by_uid(self, uid):
            return {'pc-ara': ara, 'npc-gob-1': gob}.get(str(uid))

    class FakeMap:
        session = FakeSession()
        entities = [ara, gob]

    tokens = {
        'pc-ara': {'src': 'models/tokens/ara.glb', 'height': 6.5},
        'npc-gob-1': {'src': 'models/tokens/ara.glb', 'height': 3},
    }
    tiles = [
        {'entity': {'name': 'Ara'}, 'id': 'pc-ara', 'x': 1, 'y': 2, 'name': 'Ara'},
        {'entity': {'name': 'Gob'}, 'id': 'npc-gob-1', 'x': 3, 'y': 4, 'name': 'Gob'},
    ]
    out = entities_from_tiles(tiles, battle_map=FakeMap(), tokens=tokens)
    by_uid = {e['uid']: e for e in out}
    assert by_uid['pc-ara']['model']['size_scale'] == 2.0
    assert 'size_scale' not in by_uid['npc-gob-1']['model']
