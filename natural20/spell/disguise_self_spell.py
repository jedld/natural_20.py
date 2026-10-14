"""Disguise Self — 1st-level illusion (SRD, 1 hour).

The caster looks like someone else. The spell object keeps the cosmetic
``description`` (``spell_action.disguise`` text if the caller supplies one,
else YAML ``default_disguise``) and the spell save ``dc``; ``disguise_of``
reads them back as a dict. The disguise is purely cosmetic — stats, size
class and equipment don't change.

A creature that studies the caster can see through it with an Intelligence
(Investigation) check against that DC: ``see_through_disguise``. Physical
contact giving the illusion away is narrative only.
"""
from __future__ import annotations

from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell

EFFECT_KEY = 'disguise_self'


def _active_disguise(entity):
    for entry in (getattr(entity, 'effects', None) or {}).get(EFFECT_KEY, []) or []:
        effect = entry.get('effect')
        if isinstance(effect, DisguiseSelfSpell):
            return effect
    return None


def disguise_of(entity):
    """``{'description', 'dc', 'seen_through_by'}`` for a disguised creature, else None."""
    effect = _active_disguise(entity)
    if effect is None:
        return None
    return {
        'description': effect.description,
        'dc': int(effect.dc or 10),
        'seen_through_by': effect.seen_through(),
    }


def is_disguised(entity) -> bool:
    return _active_disguise(entity) is not None


def see_through_disguise(observer, target, battle=None):
    """Investigation check vs the disguise DC. Returns ``(success, roll)``;
    ``(True, None)`` when the target isn't disguised."""
    effect = _active_disguise(target)
    if effect is None:
        return True, None
    roll = observer.investigation_check(battle, description='dice_roll.investigation')
    dc = int(effect.dc or 10)
    success = roll.result() >= dc
    if success:
        effect.mark_seen_through(observer)
    session = getattr(target, 'session', None)
    if session is not None:
        session.event_manager.received_event({
            'event': 'disguise_check', 'source': observer, 'target': target,
            'roll': roll, 'dc': dc, 'success': success,
        })
    return success, roll


class DisguiseSelfSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.description = None
        self.dc = None
        self.seen_through_uids = ''

    def __str__(self):
        return 'disguise_self'

    def seen_through(self):
        return [u for u in str(self.seen_through_uids or '').split(',') if u]

    def mark_seen_through(self, observer):
        uid = getattr(observer, 'entity_uid', None)
        seen = self.seen_through()
        if uid and uid not in seen:
            self.seen_through_uids = ','.join(seen + [uid])

    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = self.source
        return action

    def resolve(self, entity, battle, spell_action, battle_map):
        description = (getattr(spell_action, 'disguise', None)
                       or self.properties.get('default_disguise')
                       or 'an unremarkable traveler')
        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        return [{
            'type': 'disguise_self',
            'source': entity,
            'target': entity,
            'effect': self,
            'description': str(description),
            'dc': dc,
            'spell': self.properties,
        }]

    @staticmethod
    def disguise_self(entity, opts=None):
        return True

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'disguise_self':
            return None
        source, effect = item['source'], item['effect']
        session = session or (battle.session if battle is not None else source.session)
        duration = int(effect.properties.get('duration_seconds', 3600))
        source.remove_effect(EFFECT_KEY)
        effect.description = item['description']
        effect.dc = int(item['dc'])
        source.add_casted_effect({'target': source, 'effect': effect,
                                  'expiration': session.game_time + duration})
        source.register_effect(EFFECT_KEY, DisguiseSelfSpell, effect=effect, source=source,
                               duration=duration)
        session.event_manager.received_event({
            'event': 'disguise_self', 'source': source, 'target': source,
            'description': item['description'],
        })
        return source
