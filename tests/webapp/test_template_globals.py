"""Unit tests for webapp template global helpers."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

from webapp.blueprints.helpers.template_globals import format_languages  # noqa: E402


class _EntityWithLanguages:
    def languages(self):
        return ['common', 'elvish', 'dwarvish']


class _EntityFromProperties:
    properties = {'languages': ['goblin', 'orcish']}


def test_format_languages_from_method():
    assert format_languages(_EntityWithLanguages()) == 'Common, Elvish, Dwarvish'


def test_format_languages_from_properties_fallback():
    assert format_languages(_EntityFromProperties()) == 'Goblin, Orcish'


def test_format_languages_empty():
    class Empty:
        properties = {}

        def languages(self):
            return []

    assert format_languages(Empty()) == ''
