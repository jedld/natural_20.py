"""Tests for NPC image gallery metadata and portrait resolution."""

from natural20.entity import Entity


def _gallery_npc():
    entity = Entity('Pip', 'barmaid', attributes={})
    entity.properties = {
        'profile_image': 'portraits/portrait_pip.jpg',
        'image_gallery': [
            {
                'id': 'portrait',
                'label': 'Portrait',
                'image': 'portraits/portrait_pip.jpg',
                'description': 'Close-up portrait.',
            },
            {
                'id': 'full_body',
                'label': 'Full Body',
                'image': 'portraits/full_body_pip.jpg',
                'description': 'Full body tavern view.',
            },
        ],
    }
    return entity


def test_image_gallery_returns_metadata():
    gallery = _gallery_npc().image_gallery()
    assert len(gallery) == 2
    assert gallery[1]['id'] == 'full_body'
    assert gallery[1]['description'] == 'Full body tavern view.'


def test_resolve_gallery_image_by_id():
    entity = _gallery_npc()
    assert entity.resolve_gallery_image('full_body') == 'portraits/full_body_pip.jpg'
    assert entity.resolve_gallery_image('missing') == 'portraits/portrait_pip.jpg'


def test_sheet_images_derives_from_gallery():
    sheet = _gallery_npc().sheet_images()
    assert len(sheet) == 2
    assert sheet[0]['description'] == 'Close-up portrait.'


def test_send_conversation_records_gallery_image_id():
    entity = _gallery_npc()
    entity.session = type('S', (), {'event_manager': type('E', (), {'received_event': lambda self, event: None})()})()
    entity.session.map_for_entity = lambda ent: None
    target = Entity('Guest', 'guest', attributes={})
    target.session = entity.session
    entity.send_conversation(
        'Hello there.',
        targets=[target],
        gallery_image_id='full_body',
    )
    assert entity.conversation_buffer[-1]['gallery_image_id'] == 'full_body'
