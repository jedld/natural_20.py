import uuid
import types
from natural20.entity_registry import EntityRegistry


def test_register_and_get_by_uid():
    reg = EntityRegistry()
    e = types.SimpleNamespace(entity_uid=str(uuid.uuid4()))
    uid = reg.register(e)
    assert isinstance(uid, str)
    assert reg.get(uid) is e
    assert reg.get_uid(e) == uid


def test_register_assigns_uid_when_missing():
    reg = EntityRegistry()
    e = types.SimpleNamespace()
    uid = reg.register(e)
    assert isinstance(uid, str)
    assert hasattr(e, 'entity_uid')
    assert reg.get(uid) is e
    assert reg.get_uid(e) == uid


def test_unregister():
    reg = EntityRegistry()
    e = types.SimpleNamespace(entity_uid=str(uuid.uuid4()))
    uid = reg.register(e)
    assert reg.get(uid) is e
    reg.unregister(e)
    assert reg.get(uid) is None
