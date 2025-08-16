import pytest

from natural20.uid_containers import ObjectsGrid, TokensGrid, EntitiesUIDMap


class FakeRegistry:
    def __init__(self):
        self._uid_to_obj = {}
        self._obj_to_uid = {}

    def get(self, uid):
        return self._uid_to_obj.get(str(uid))

    def register(self, obj):
        uid = getattr(obj, 'entity_uid', None)
        if uid is None:
            uid = f"uid-{len(self._uid_to_obj)+1}"
            setattr(obj, 'entity_uid', uid)
        self._uid_to_obj[str(uid)] = obj
        self._obj_to_uid[obj] = str(uid)
        return str(uid)

    def get_uid(self, obj):
        uid = getattr(obj, 'entity_uid', None)
        if uid is not None:
            return str(uid)
        return self._obj_to_uid.get(obj)

    def unregister(self, obj_or_uid):
        if isinstance(obj_or_uid, str):
            uid = obj_or_uid
        else:
            uid = getattr(obj_or_uid, 'entity_uid', None) or self._obj_to_uid.get(obj_or_uid)
        if uid is None:
            return
        uid = str(uid)
        obj = self._uid_to_obj.pop(uid, None)
        if obj is not None:
            self._obj_to_uid.pop(obj, None)


class FakeSession:
    def __init__(self):
        self.entity_registry = FakeRegistry()

    def register_entity(self, obj):
        return self.entity_registry.register(obj)

    def uid_for(self, obj):
        return self.entity_registry.get_uid(obj)


class Dummy:
    def __init__(self, uid):
        self.entity_uid = str(uid)


class TestObjectsGridSemantics:
    def test_bounds_and_membership(self):
        s = FakeSession()
        grid = ObjectsGrid(s, 3, 2)

        # Bounds
        with pytest.raises(IndexError):
            _ = grid[-1]
        with pytest.raises(IndexError):
            _ = grid[3]
        with pytest.raises(IndexError):
            _ = grid[0][-1]
        with pytest.raises(IndexError):
            _ = grid[0][2]

        # Insert and membership
        a = Dummy('a')
        b = Dummy('b')
        grid[1][1].append(a)
        grid[2][0].append(b)
        assert a in grid
        assert b in grid

        # Retrieval via proxy
        assert list(grid[1][1])[0] is a
        assert grid[1][1][0] is a

        # Remove updates membership
        grid[1][1].remove(a)
        assert a not in grid

    def test_clear_and_string_uid_append(self):
        s = FakeSession()
        grid = ObjectsGrid(s, 1, 1)
        # Append by raw UID string without registering entity
        raw_uid = 'ghost-uid'
        grid[0][0].append(raw_uid)
        assert raw_uid in grid  # membership via UID string works
        # Proxy tries to resolve to entity -> None
        assert grid[0][0][0] is None
        # Clear removes all
        grid[0][0].clear()
        assert raw_uid not in grid


class TestTokensGridSemantics:
    def test_bounds_membership_and_proxy(self):
        s = FakeSession()
        tokens = TokensGrid(s, 2, 2)

        # Bounds
        with pytest.raises(IndexError):
            _ = tokens[-1]
        with pytest.raises(IndexError):
            _ = tokens[2]
        with pytest.raises(IndexError):
            _ = tokens[0][-1]
        with pytest.raises(IndexError):
            _ = tokens[0][2]

        ent = Dummy('x')
        tokens[0][0] = {'entity': ent, 'token': 'X'}

        # Membership via entity uid
        assert ent in tokens

        # Proxy access resolves entity
        cell = tokens[0][0]
        assert cell['entity'] is ent
        assert cell['token'] == 'X'

        # Clear
        tokens[0][0] = None
        assert ent not in tokens

    def test_set_with_entity_uid_only(self):
        s = FakeSession()
        tokens = TokensGrid(s, 1, 1)
        tokens[0][0] = {'entity_uid': 'uid-123', 'token': '*'}
        # Membership by UID string
        assert 'uid-123' in tokens
        # Proxy resolves entity -> None since not registered
        cell = tokens[0][0]
        assert cell['entity'] is None
        assert cell['token'] == '*'


class TestEntitiesUIDMapSemantics:
    def test_uid_map_registers_and_resolves(self):
        s = FakeSession()
        a = Dummy('A')
        b = Dummy('B')
        # Construct from object-keyed mapping should seed registry and store by UID
        m = EntitiesUIDMap(s, {a: 1})
        assert m[a] == 1
        # Set by live object
        m[b] = 2
        assert m[b] == 2
        # as uid dict exposes UID keys
        uid_dict = m.as_uid_dict()
        assert 'A' in uid_dict and 'B' in uid_dict
        assert uid_dict['A'] == 1 and uid_dict['B'] == 2

    def test_get_set_delete_by_uid_and_iteration_stability(self):
        s = FakeSession()
        a = Dummy('A')
        b = Dummy('B')
        m = EntitiesUIDMap(s)
        # Set by UID directly
        m['A'] = {'pos': [1, 2]}
        m[b] = {'pos': [3, 4]}
        assert m.get_by_uid('A') == {'pos': [1, 2]}
        # set_by_uid updates value
        m.set_by_uid('A', {'pos': [9, 9]})
        assert m['A'] == {'pos': [9, 9]}
        # Iteration yields live objects only (b present, 'A' missing in registry)
        # Register a so it appears in iteration
        s.register_entity(a)
        it_objs = list(iter(m))
        assert a in it_objs and b in it_objs
        # Simulate GC/removal from registry for a
        s.entity_registry.unregister(a)
        it_objs2 = list(iter(m))
        assert a not in it_objs2 and b in it_objs2
        # Delete by UID and by object
        del m['A']
        assert m.get_by_uid('A') is None
        del m[b]
        assert m.get_by_uid('B') is None
