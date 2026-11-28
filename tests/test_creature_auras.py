"""Unit tests for the generic creature-aura render channel
(natural20/utils/creature_auras.py): emanation zones (battle and
environment) plus YAML/class-feature support auras."""
from natural20.utils.creature_auras import creature_auras


class FakeZone:
    def __init__(self, owner, name, radius_ft, shape='emanation'):
        self.owner = owner
        self.name = name
        self.radius_ft = radius_ft
        self.shape = shape


class FakeBattle:
    def __init__(self, zones=None):
        self.active_zones = zones or []


class FakeMap:
    def __init__(self, zones=None):
        self.environment_zones = zones or []


class FakeEntity:
    def __init__(self, props=None):
        self.properties = props or {}

    def dead(self):
        return False

    def conscious(self):
        return True


def test_emanation_zones_become_rings():
    caster = FakeEntity()
    battle = FakeBattle([
        FakeZone(caster, 'investiture_of_flame', 5),
        FakeZone(caster, 'spirit_guardians', 15),
        FakeZone(FakeEntity(), 'wall_of_thorns', 20, shape='wall'),
    ])
    auras = creature_auras(caster, battle=battle, feet_per_grid=5)
    assert auras == [
        {'name': 'investiture_of_flame', 'radius_ft': 5, 'radius_tiles': 1},
        {'name': 'spirit_guardians', 'radius_ft': 15, 'radius_tiles': 3},
    ]


def test_out_of_combat_environment_zones_count_too():
    caster = FakeEntity()
    zone = FakeZone(caster, 'investiture_of_flame', 5)
    battle = FakeBattle([])
    battle_map = FakeMap([zone])
    auras = creature_auras(caster, battle=battle, battle_map=battle_map)
    assert [a['name'] for a in auras] == ['investiture_of_flame']


def test_duplicate_zones_dedupe():
    caster = FakeEntity()
    battle = FakeBattle([
        FakeZone(caster, 'investiture_of_flame', 5),
        FakeZone(caster, 'investiture_of_flame', 5),
    ])
    assert len(creature_auras(caster, battle=battle)) == 1


def test_yaml_support_auras_included(tmp_path=None):
    from natural20.utils.auras import active_auras_of
    entity = FakeEntity({'auras': [{'name': 'aura_of_warding', 'range': 10}]})
    assert [a['name'] for a in active_auras_of(entity)] == ['aura_of_warding']
    auras = creature_auras(entity, feet_per_grid=5)
    assert auras == [
        {'name': 'aura_of_warding', 'radius_ft': 10, 'radius_tiles': 2},
    ]


def test_down_owner_projects_nothing():
    class Dead(FakeEntity):
        def dead(self):
            return True
    entity = Dead({'auras': [{'name': 'aura_of_warding', 'range': 10}]})
    assert creature_auras(entity) == []
