"""Effects that last "until the start of <creature>'s next turn".

``schedule(owner, effect, holder)`` remembers ``effect`` (applied to
``holder``) in ``owner.attributes['until_next_turn']``; when ``owner``'s turn
starts, ``Battle.start_turn`` calls ``expire_until_next_turn`` and each
effect is ended through ``holder.dismiss_effect(effect)`` (or the effect's own
``end(reason)``).
"""

from __future__ import annotations

KEY = 'until_next_turn'


def schedule(owner, effect, holder=None):
    attrs = getattr(owner, 'attributes', None)
    if not isinstance(attrs, dict):
        return
    entries = list(attrs.get(KEY) or [])
    entries.append({'effect': effect, 'holder': holder or owner})
    attrs[KEY] = entries


def expire_until_next_turn(owner, battle=None):
    attrs = getattr(owner, 'attributes', None)
    if not isinstance(attrs, dict) or not attrs.get(KEY):
        return
    entries = attrs.pop(KEY) or []
    for entry in entries:
        effect = entry.get('effect')
        holder = entry.get('holder') or owner
        end = getattr(effect, 'end', None)
        if callable(end):
            end('next_turn')
        elif hasattr(holder, 'dismiss_effect'):
            holder.dismiss_effect(effect)
