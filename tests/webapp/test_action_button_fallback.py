import os
import sys

from flask import render_template

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app


class FakeInteractAction:
    as_bonus_action = False
    action_type = 'interact'
    disabled = False
    disabled_reason = None
    object_action = ['travel', {}]
    target = None
    thrown = False
    using = None

    def to_h(self):
        return {}

    def label(self):
        return 'Use dumbwaiter'

    def button_label(self):
        return 'Servants Quarters'

    def button_image(self):
        return 'missing_dumbwaiter_asset'


def test_action_button_renders_text_fallback_for_missing_icon():
    with app.test_request_context('/'):
        html = render_template('_action_button.html', action=FakeInteractAction())

    assert 'action-image-fallback' in html
    assert 'Servants Quarters' in html
    assert 'missing_dumbwaiter_asset.png' in html
    assert "onerror=\"this.style.display='none'; this.nextElementSibling.style.display='flex';\"" in html