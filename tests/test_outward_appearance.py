from unittest.mock import Mock

from natural20.utils.outward_appearance import (
    derive_outward_appearance,
    explicit_outward_appearance,
    resolve_outward_appearance,
)


def test_explicit_outward_appearance_prefers_outward_appearance_key():
    props = {
        'appearance': 'legacy appearance',
        'outward_appearance': 'A scarred dwarf in soot-stained plate.',
    }
    assert explicit_outward_appearance(props) == 'A scarred dwarf in soot-stained plate.'


def test_derive_outward_appearance_uses_race_class_and_gear():
    entity = Mock()
    entity.object.return_value = False
    entity.properties = {'race': 'halfling', 'subrace': 'lightfoot', 'size': 'small'}
    entity.race.return_value = 'halfling'
    entity.class_descriptor.return_value = 'rogue-2'
    entity.class_and_level.return_value = [('rogue', 2)]
    entity.equipped_items.return_value = [
        {'label': 'Leather Armor', 'type': 'light_armor'},
        {'label': 'Shortbow', 'type': 'ranged_weapon'},
    ]

    text = derive_outward_appearance(entity)

    assert 'halfling' in text
    assert 'lightfoot' in text
    assert 'rogue' in text
    assert 'Leather Armor' in text
    assert 'Shortbow' in text


def test_resolve_outward_appearance_uses_explicit_yaml_value():
    entity = Mock()
    entity.properties = {'outward_appearance': 'A hooded figure with silver rings.'}
    entity.object.return_value = False

    assert resolve_outward_appearance(entity) == 'A hooded figure with silver rings.'


def test_resolve_outward_appearance_falls_back_to_derivation():
    entity = Mock()
    entity.properties = {'race': ['humanoid', 'human'], 'kind': 'Guard'}
    entity.object.return_value = False
    entity.race.return_value = ['humanoid', 'human']
    entity.class_and_level.return_value = [('Guard', None)]
    entity.class_descriptor.return_value = ''
    entity.equipped_items.return_value = []
    entity.has_notes = Mock(return_value=False)

    text = resolve_outward_appearance(entity)

    assert 'human' in text.lower()


def test_conversation_self_appearance_prefers_explicit_yaml():
    entity = Mock()
    entity.properties = {
        'outward_appearance': 'Purple robes and a violet staff.',
        'race': ['human'],
    }
    entity.object.return_value = False
    entity.equipped_items.return_value = []
    entity.has_notes = Mock(return_value=False)

    from natural20.utils.outward_appearance import conversation_self_appearance

    assert conversation_self_appearance(entity) == 'Purple robes and a violet staff.'
