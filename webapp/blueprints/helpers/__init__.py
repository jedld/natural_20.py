"""Helper modules extracted from the monolithic app.py.

These modules provide pure-function utilities that blueprints and app.py
share.  They must NOT import from ``webapp.app`` to avoid circular
dependencies.
"""
