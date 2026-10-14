"""Spells whose effect is delivered by a weapon hit (Ensnaring Strike, Hail of Thorns, ...).

Spell YAML declares the trigger::

    weapon_hit:
      weapon: ranged        # ranged | melee | any — which weapon hit qualifies
      timing: after_hit     # after_hit | next_hit

* ``after_hit`` (SRD 5.2 / 2024): the spell is a Bonus Action taken right
  after the caster hits with a qualifying weapon. ``WeaponHitSpellOffer`` (an
  ``on_attack_hit`` hook installed on every player character by
  ``install_weapon_hit_spell_offer``) offers one ``WeaponHitSpellCastAction``
  per usable slot level through ``controller.select_reaction``. A direct cast
  from the spell list is not allowed (``SpellAction.can_cast``).
* ``next_hit`` (2014): the spell is cast normally (Bonus Action); it arms the
  caster and the effect fires on the next qualifying hit while it lasts.

Subclasses of ``WeaponHitSpell`` implement ``on_weapon_hit(caster, target,
hit_result, slot_level, battle)`` returning result items (``spell_damage``
items and/or items whose ``effect`` is a Spell, applied by
``SpellAction.apply`` when the attack commits).
"""
from __future__ import annotations

from natural20.action import Action, AsyncReactionHandler
from natural20.spell.spell import Spell, consume_resource

WEAPON_HIT_KEY = 'weapon_hit'
ARMED_EFFECT = 'weapon_hit_spell_armed'


def weapon_hit_config(spell_details) -> dict:
    cfg = (spell_details or {}).get(WEAPON_HIT_KEY)
    return cfg if isinstance(cfg, dict) else {}


def weapon_hit_timing(spell_details):
    cfg = weapon_hit_config(spell_details)
    return cfg.get('timing', 'after_hit') if cfg else None


def hit_weapon_kind(entity, hit_result):
    """``'melee'`` / ``'ranged'`` for a weapon (or natural weapon) hit, else None.

    A thrown melee weapon is still a melee weapon."""
    meta = hit_result.get('npc_action')
    weapon_key = hit_result.get('weapon')
    if not meta and weapon_key:
        if isinstance(weapon_key, dict):
            meta = weapon_key
        else:
            try:
                meta = entity.session.load_weapon(weapon_key)
            except Exception:
                meta = None
    if not isinstance(meta, dict):
        return None
    kind = meta.get('type')
    if kind == 'melee_attack':
        return 'melee'
    if kind == 'ranged_attack':
        return 'ranged'
    return None


def weapon_qualifies(spell_details, entity, hit_result) -> bool:
    kind = hit_weapon_kind(entity, hit_result)
    if kind is None:
        return False
    wanted = weapon_hit_config(spell_details).get('weapon', 'any')
    return wanted in (None, 'any') or wanted == kind


def caster_save_dc(entity, spell_details, casting_class=None):
    from natural20.spell.hold_person_spell import HoldPersonSpell

    class _Probe:
        spell = spell_details
        spellcasting_class = casting_class

    return entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, _Probe()))


def _spell_id(spell_details):
    return (spell_details or {}).get('id')


class WeaponHitSpell(Spell):
    """Base class for weapon-hit spells (see module docstring)."""

    SLUG = None

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.cast_level = int((details or {}).get('level') or 1)
        self.casting_class = None
        self.armed = False
        self._instance_id = f"{self.SLUG or spell_name}:{id(self)}"

    @property
    def id(self):
        return self._instance_id

    def __str__(self):
        return str(self.SLUG or super().__str__())

    def timing(self):
        return weapon_hit_timing(self.properties)

    def save_dc(self, caster=None):
        return caster_save_dc(caster or self.source, self.properties, self.casting_class)

    def on_weapon_hit(self, caster, target, hit_result, slot_level, battle):  # pragma: no cover - override
        return []

    def keeps_concentration_after_trigger(self):
        """2014 ``next_hit`` mode: whether the spell lasts after it fires."""
        return False

    # --- casting from the spell list (next_hit mode) ---------------------

    def build_map(self, orig_action):
        action = orig_action.clone() if hasattr(orig_action, 'clone') else orig_action
        action.target = self.source
        return action

    def resolve(self, entity, battle, spell_action, battle_map):
        if self.timing() != 'next_hit':
            return []
        self.cast_level = int(getattr(spell_action, 'at_level', None) or self.cast_level)
        self.casting_class = getattr(spell_action, 'spellcasting_class', None)
        return [{
            'type': ARMED_EFFECT,
            'source': entity,
            'target': entity,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != ARMED_EFFECT or not isinstance(item.get('effect'), WeaponHitSpell):
            return None
        source = item['source']
        effect = item['effect']
        session = session or (battle.session if battle is not None else source.session)
        duration = int(effect.properties.get('duration_seconds', 60) or 60)
        effect.armed = True
        effect.target = source
        source.add_casted_effect({'target': source, 'effect': effect,
                                  'expiration': session.game_time + duration})
        source.register_effect(ARMED_EFFECT, WeaponHitSpell, effect=effect, source=source,
                               duration=duration)
        effect._register_armed_hook(source, duration)
        if effect.properties.get('concentration'):
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)
        session.event_manager.received_event({
            'event': 'spell_buf', 'spell': effect, 'source': source, 'target': source,
        })
        return source

    @staticmethod
    def weapon_hit_spell_armed(entity, opt=None):
        return True

    def _register_armed_hook(self, source, duration=None):
        source.register_event_hook('on_attack_hit', self, 'armed_on_attack_hit',
                                   effect=self, source=source, duration=duration)

    def armed_on_attack_hit(self, entity, opts=None):
        opts = opts or {}
        if not self.armed or entity is not self.source:
            return []
        hit_result = opts.get('result') or {}
        target = hit_result.get('target')
        battle = hit_result.get('battle')
        if not hit_result.get('hit?') or target is None:
            return []
        if not weapon_qualifies(self.properties, entity, hit_result):
            return []
        self.armed = False
        entity.entity_event_hooks['on_attack_hit'] = [
            h for h in entity.entity_event_hooks.get('on_attack_hit', []) if h.get('effect') is not self
        ]
        if ARMED_EFFECT in entity.effects:
            entity.effects[ARMED_EFFECT] = [
                f for f in entity.effects[ARMED_EFFECT] if f.get('effect') is not self
            ]
        items = list(self.on_weapon_hit(entity, target, hit_result, self.cast_level, battle) or [])
        if not self.keeps_concentration_after_trigger():
            items.append({'type': 'dismiss_effect', 'source': entity, 'target': entity, 'effect': self})
        return items

    def restore_hooks(self):
        if self.armed and self.source is not None and hasattr(self.source, 'register_event_hook'):
            self._register_armed_hook(self.source)

    def dismiss(self, entity, _descriptor=None, opts=None):
        self.armed = False


class WeaponHitSpellCastAction(Action):
    """Bonus action: cast an ``after_hit`` weapon-hit spell on the creature just hit."""

    def __init__(self, session, source, spell_details, slot_level, target, hit_result,
                 casting_class=None):
        super().__init__(session, source, _spell_id(spell_details) or 'weapon_hit_spell')
        self.spell_details = spell_details or {}
        self.slot_level = int(slot_level or self.spell_details.get('level') or 1)
        self.target = target
        self.hit_result = hit_result or {}
        self.casting_class = casting_class
        self.as_bonus_action = True

    def spell_label(self):
        return self.spell_details.get('label') or self.spell_details.get('name') or self.action_type

    def label(self):
        return f"{self.spell_label()} (Level {self.slot_level})"

    def button_label(self):
        return self.label()

    def name(self):
        return self.label()

    def __str__(self):
        return f"WeaponHitSpell({self.action_type}@{self.slot_level})"

    __repr__ = __str__

    def resolve(self, session, map=None, opts=None):
        from natural20.utils.spell_loader import load_spell_class, resolve_spell_class_key

        battle = (opts or {}).get('battle') or self.hit_result.get('battle')
        spell_id = _spell_id(self.spell_details)
        class_key = resolve_spell_class_key(spell_id, self.spell_details)
        spell = load_spell_class(class_key)(self.session, self.source, class_key, self.spell_details)
        spell.cast_level = self.slot_level
        spell.casting_class = self.casting_class
        items = list(spell.on_weapon_hit(self.source, self.target, self.hit_result,
                                         self.slot_level, battle) or [])
        consume_resource(battle, self.source, self.spell_details, cast_level=self.slot_level,
                         casting_class=self.casting_class)
        self.source.break_stealth() if hasattr(self.source, 'break_stealth') else None
        self.result = [{
            'type': 'weapon_hit_spell_cast',
            'source': self.source,
            'target': self.target,
            'spell': self.spell_details,
            'slot_level': self.slot_level,
        }] + items
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'weapon_hit_spell_cast':
            return None
        session = session or (battle.session if battle is not None else item['source'].session)
        session.event_manager.received_event({
            'event': 'weapon_hit_spell_cast',
            'source': item['source'],
            'target': item['target'],
            'spell': item['spell'].get('name') or item['spell'].get('label'),
            'slot_level': item.get('slot_level'),
        })
        return None


def castable_slot_levels(entity, battle, spell_details):
    """``[(slot_level, casting_class), ...]`` the caster can spend right now."""
    from natural20.utils.action_restrictions import is_restricted
    from natural20.utils.spell_requirements import environment_issue, spells_this_turn_issue

    if is_restricted(entity, 'spell'):
        return []
    if environment_issue(entity, spell_details, battle):
        return []
    base = int(spell_details.get('level') or 1)
    options = []
    seen = set()
    for klass in entity.spell_list_classes_for(spell_details):
        for level, qty in sorted((getattr(entity, 'spell_slots', {}) or {}).get(klass, {}).items()):
            if level >= base and qty > 0 and level not in seen:
                if spells_this_turn_issue(entity, battle, level, 'bonus_action'):
                    continue
                seen.add(level)
                options.append((level, klass))
    return sorted(options)


class WeaponHitSpellOffer:
    """``on_attack_hit`` hook offering prepared ``after_hit`` weapon-hit spells."""

    def __init__(self, owner):
        self.owner = owner

    def __str__(self):
        return 'weapon_hit_spells'

    def candidate_spells(self, entity):
        prepared = entity.prepared_spells() if hasattr(entity, 'prepared_spells') else []
        out = []
        for spell_id in prepared or []:
            try:
                details = entity.session.load_spell(spell_id)
            except Exception:
                continue
            if details and weapon_hit_timing(details) == 'after_hit':
                out.append(details)
        return out

    def on_attack_hit(self, entity, opts=None):
        opts = opts or {}
        if entity is not self.owner:
            return []
        hit_result = opts.get('result') or {}
        battle = hit_result.get('battle')
        target = hit_result.get('target')
        if not hit_result.get('hit?') or battle is None or target is None:
            return []
        if entity.total_bonus_actions(battle) <= 0:
            return []
        valid = []
        for details in self.candidate_spells(entity):
            if not weapon_qualifies(details, entity, hit_result):
                continue
            for level, klass in castable_slot_levels(entity, battle, details):
                valid.append(WeaponHitSpellCastAction(entity.session, entity, details, level, target,
                                                      hit_result, casting_class=klass))
        if not valid:
            return []
        stored = opts.get('stored_reaction')
        controller = battle.controller_for(entity)
        if stored not in (None, False):
            selected = stored
        elif controller is None:
            selected = valid[0]
        else:
            selected = controller.select_reaction(entity, battle, battle.map_for(entity), valid, {
                'type': 'weapon_hit_spell',
                'trigger': 'on_attack_hit',
                'source': entity,
                'target': target,
                'result': hit_result,
            })
        if hasattr(selected, 'send'):
            raise AsyncReactionHandler(entity, selected, opts.get('action'), 'on_attack_hit')
        if isinstance(selected, int) and 0 <= selected < len(valid):
            selected = valid[selected]
        if not isinstance(selected, WeaponHitSpellCastAction):
            return []
        resolved = selected.resolve(entity.session, battle.map_for(entity), {'battle': battle})
        return resolved.result or []


def install_weapon_hit_spell_offer(entity):
    hooks = (getattr(entity, 'entity_event_hooks', None) or {}).get('on_attack_hit', [])
    if any(isinstance(h.get('handler'), WeaponHitSpellOffer) for h in hooks):
        return
    entity.register_event_hook('on_attack_hit', WeaponHitSpellOffer(entity), 'on_attack_hit')
