"""Rules oracle: authoritative "what this actually does" text for generative prompts.

Generative strategist LLMs hallucinate D&D 5e mechanics - Second Wind granting
advantage, Action spells cast as bonus actions, imagined multiattacks, invented
spell effects. This module answers each legal option (and each spell, effect
or trait *seen* on other combatants) with the rules the engine actually
implements, gathered from:

* Spell / item YAML ``description`` (templates, expansion packs, campaigns)
  plus the mechanics keys the engine reads (``casting_time``, ``range``,
  ``components``, ``concentration``).
* NPC attack YAML entries: to-hit, damage dice, riders (``additional_damage``,
  ``grapple_instead``, ``recharge``) synthesized straight from the config.
* Monster trait configs (``regeneration``, ``legendary_resistance``, ...) via
  :mod:`natural20.utils.monster_traits`.
* A small built-in table of SRD rules for generic actions and class features.

Everything here is campaign-agnostic: campaign-flavored rules arrive through
their YAML ``description`` fields, never through this module. The text is
capped per entry and per section so the strategist prompt stays bounded
(``N20_STRATEGIST_ORACLE=0`` disables it entirely).
"""

import os
import re
from typing import Any, Dict, List, Optional

MAX_ENTRY_CHARS = 420          # one option / one observed entry
MAX_OPTIONS_BUDGET = 2600      # whole "rules for those options" section
MAX_OBSERVED_BUDGET = 1800     # whole "seen in this fight" section
MAX_OBSERVED_ITEMS = 14

_CASTING_TIME_TEXT = {
    '1:action': 'Action',
    '1:bonus_action': 'bonus action',
    '1:reaction': 'reaction',
    'instant:no_action': 'no action (instantaneous)',
}

# SRD-only one-liners for generic actions and common class features whose
# mechanics live in Python rather than YAML descriptions.
FEATURE_RULES: Dict[str, str] = {
    'attack': ("Attack action: one weapon attack (melee within 5 ft or ranged "
               "within the weapon's range; disadvantage on ranged attacks with "
               "an enemy within 5 ft). Extra attacks come only from the Extra "
               "Attack feature listed on the sheet."),
    'dash': ("Dash: take the Attack-amount of movement again this turn "
             "(double speed), plus any unspent movement."),
    'dodge': ("Dodge: attacks against you have disadvantage and you make "
              "Dex saves with advantage until your next turn; ends if you "
              "become incapacitated."),
    'disengage': ("Disengage: your movement does not provoke opportunity "
                  "attacks for the rest of the turn."),
    'hide': ("Hide: Dexterity (Stealth) vs observers' Perception; you are "
             "hidden only if no enemy has a clear sight line and is not "
             "actively searching; failing leaves you plainly visible."),
    'help': ("Help: aid one creature within 60 ft (advantage on its next "
             "ability check against you) or try to heal it; a creature at 0 "
             "HP is stabilized but not healed."),
    'ready': ("Ready: choose a trigger and a reaction-like response; the "
              "trigger must be a full turn's wait and the reaction is spent."),
    'grapple': ("Grapple: STR (Athletics) vs the target's STR (Athletics) or "
                "DEX (Acrobatics); on success the target is grappled (speed 0) "
                "until you release it, stop meeting the conditions, or move "
                "out of reach; dragging halves your speed."),
    'shove': ("Shove: STR (Athletics) vs the target's STR (Athletics) or DEX "
              "(Acrobatics); on success the target is pushed 5 ft or knocked "
              "prone."),
    'second_wind': ("Second Wind (bonus action, once per short rest): regain "
                    "hit points only - it grants no advantage, no temporary "
                    "hit points and no other benefit."),
    'action_surge': ("Action Surge: gain ONE additional Action on this turn, "
                     "usable for another Attack action or an Action-time "
                     "spell; it does NOT create a bonus action and does not "
                     "change spellcasting rules."),
    'cunning_action': ("Cunning Action (bonus action): Dash, Disengage or "
                       "Hide using only the bonus action."),
    'use_item': ("Use an item: some items need an Action (potions, most "
                 "wands), others are free or bonus-action - read the item's "
                 "own description below."),
    'spell_generic': ("Casting a spell uses its listed casting time; a spell "
                      "requiring a bonus action means the only other spell "
                      "this turn is a cantrip with a casting time of 1 action."),
    'opportunity_attack': ("Opportunity attack: one melee attack against a "
                           "creature that leaves your reach without Disengaging."),
}


def oracle_enabled() -> bool:
    return (os.environ.get('N20_STRATEGIST_ORACLE') or '1').strip().lower() \
        not in ('0', 'no', 'false', 'off')


def _budget(env_name: str, default: int) -> int:
    raw = os.environ.get(env_name)
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            return default
    return default


def _compact(text: Any) -> str:
    """One-line, whitespace-collapsed rendering of a YAML block scalar."""
    if not isinstance(text, str):
        return ''
    return re.sub(r'\s+', ' ', text).strip()


def _cut(text: str, cap: int = MAX_ENTRY_CHARS) -> str:
    text = text.strip()
    if len(text) <= cap:
        return text
    return text[:cap].rstrip() + '...'


def _props_dict(obj: Any) -> Optional[Dict[str, Any]]:
    """Normalize spell/item/npc-action sources to a plain meta dict."""
    if isinstance(obj, dict):
        return obj or None
    props = getattr(obj, 'properties', None)
    if isinstance(props, dict) and props:
        return props
    meta = getattr(obj, 'meta', None)
    if isinstance(meta, dict) and meta:
        return meta
    return None


# --------------------------------------------------------------------- #
# Per-option rules                                                      #
# --------------------------------------------------------------------- #

def spell_rules(props: Dict[str, Any]) -> Optional[str]:
    """Compact authoritative rules line for a spell/item meta dict."""
    bits: List[str] = []
    ct = props.get('casting_time')
    if ct:
        bits.append(f"casting time: {_CASTING_TIME_TEXT.get(str(ct), ct)}")
    comps = props.get('components')
    if isinstance(comps, list) and comps:
        bits.append("components " + ",".join(str(c)[0].upper() for c in comps))
    rng = props.get('range')
    if rng not in (None, '', 'self'):
        bits.append(f"range {rng} ft")
    if props.get('concentration'):
        dur = props.get('duration') or ''
        bits.append(f"concentration{', ' + str(dur) if dur else ''}")
    desc = _compact(props.get('description'))
    if not desc and not bits:
        return None
    if desc:
        bits.append(desc)
    return _cut('; '.join(bits))


def npc_attack_rules(npc_action: Dict[str, Any]) -> Optional[str]:
    """Rules line for an NPC attack option, synthesized from its YAML."""
    bits: List[str] = []
    desc = _compact(npc_action.get('description'))
    if desc:
        bits.append(desc)
    if npc_action.get('attack') is not None:
        bits.append(f"{int(npc_action['attack']):+d} to hit")
    die = npc_action.get('damage_die') or npc_action.get('damage')
    dtype = npc_action.get('damage_type')
    if die:
        bits.append(f"damage {die}{' ' + str(dtype) if dtype else ''} damage")
    rng = npc_action.get('range')
    if rng:
        rmax = npc_action.get('range_max')
        bits.append(f"range {rng} ft" + (f"/{rmax} ft" if rmax else ''))
    if npc_action.get('reach'):
        bits.append(f"reach {npc_action['reach']} ft")
    try:
        from natural20.utils.monster_traits import (additional_damage_entries,
                                                    grapple_instead_config)
        for entry in additional_damage_entries(npc_action):
            extra = _compact(entry.get('description')) or \
                f"on hit adds {entry.get('damage_die')}" \
                f"{' ' + str(entry.get('damage_type')) if entry.get('damage_type') else ''}" \
                " extra damage"
            if entry.get('life_drain'):
                extra += " (life drain: the target cannot regain those hit points until your next turn)"
            bits.append(extra)
        grapple = grapple_instead_config(npc_action)
        if grapple:
            bits.append("can grapple instead of dealing damage "
                        "(target may STR or DEX check to escape)")
    except Exception:
        pass
    if npc_action.get('recharge'):
        bits.append(f"recharge {npc_action['recharge']} (roll at the start of your turn)")
    if npc_action.get('save'):
        bits.append(f"target makes a {npc_action['save']} saving throw")
    if not bits:
        return None
    return _cut('; '.join(bits))


def _weapon_rules(source: Any, weapon_name: str) -> Optional[str]:
    try:
        for item in (source.equipped_items() or []):
            if not isinstance(item, dict):
                continue
            if str(item.get('name', '')).lower() != str(weapon_name).lower():
                continue
            meta = _props_dict(item) or item
            bits = []
            die = meta.get('damage_die') or meta.get('damage')
            dtype = meta.get('damage_type')
            if die:
                bits.append(f"{die}{' ' + str(dtype) if dtype else ''} damage")
            rng = meta.get('range')
            if rng:
                rmax = meta.get('range_max')
                bits.append(f"range {rng} ft" + (f"/{rmax} ft" if rmax else ''))
            props = meta.get('properties')
            if isinstance(props, list) and props:
                bits.append("properties: " + ", ".join(map(str, props)))
            desc = _compact(meta.get('description'))
            if desc:
                bits.append(desc)
            return _cut('; '.join(bits)) if bits else None
    except Exception:
        return None
    return None


def option_rules(action: Any) -> Optional[str]:
    """Authoritative rules text for one legal option (``None`` if unknown)."""
    if action is None:
        return None
    npc = getattr(action, 'npc_action', None)
    if isinstance(npc, dict):
        rules = npc_attack_rules(npc)
        if getattr(action, 'grapple_instead', False) and rules:
            rules += " (this option replaces the damage with a grapple attempt)"
        return rules
    spell = getattr(action, 'spell', None) or getattr(action, 'spell_action', None) \
        or (getattr(action, 'opts', None) or {}).get('spell')
    props = _props_dict(spell)
    if props and (props.get('description') or props.get('casting_time')
                  or props.get('level') is not None):
        rules = spell_rules(props)
        at_level = getattr(action, 'at_level', None)
        if rules and at_level:
            rules += f" (upcast to level {at_level} if the description scales)"
        return rules
    item = getattr(action, 'target_item', None)
    item_props = _props_dict(item)
    if item_props:
        return spell_rules(item_props)
    action_type = str(getattr(action, 'action_type', '') or '')
    if action_type in ('second_wind', 'action_surge'):
        if action_type == 'second_wind':
            source = getattr(action, 'source', None)
            die = None
            try:
                if source is not None and callable(getattr(source, 'second_wind_die', None)):
                    die = str(source.second_wind_die())
            except Exception:
                die = None
            base = FEATURE_RULES['second_wind']
            if die:
                base = base.replace('hit points only',
                                    f"{die} hit points and nothing else")
            return _cut(base)
        return _cut(FEATURE_RULES['action_surge'])
    for cls, key in (
        ('DodgeAction', 'dodge'), ('DashAction', 'dash'),
        ('DisengageAction', 'disengage'), ('HideAction', 'hide'),
        ('HelpAction', 'help'), ('ReadyAction', 'ready'),
    ):
        try:
            import importlib
            module = importlib.import_module(
                {'DodgeAction': 'natural20.actions.dodge_action',
                 'DashAction': 'natural20.actions.dash',
                 'DisengageAction': 'natural20.actions.disengage_action',
                 'HideAction': 'natural20.actions.hide_action',
                 'HelpAction': 'natural20.actions.help_action',
                 'ReadyAction': 'natural20.actions.ready_action'}[cls])
            if isinstance(action, getattr(module, cls)):
                return _cut(FEATURE_RULES[key])
        except Exception:
            continue
    using = getattr(action, 'using', None)
    if using:
        source = getattr(action, 'source', None)
        rules = _weapon_rules(source, using) if source is not None else None
        base = FEATURE_RULES['attack']
        return _cut(f"{rules}; {base}" if rules else base)
    if action_type == 'attack' or str(getattr(action, 'action_type', '')) == 'attack':
        return _cut(FEATURE_RULES['attack'])
    label = str(getattr(action, 'label', lambda: '')() or '').lower()
    feature = FEATURE_RULES.get(action_type) or FEATURE_RULES.get(label)
    return _cut(feature) if feature else None


# --------------------------------------------------------------------- #
# Seen spells, effects and traits                                       #
# --------------------------------------------------------------------- #

def _trait_lines(entity: Any) -> List[str]:
    out: List[str] = []
    try:
        from natural20.utils.monster_traits import (legendary_resistance_max,
                                                    regeneration_config,
                                                    undead_fortitude_config)
        regen = regeneration_config(entity)
        if regen:
            line = f"regenerates {regen['hp']} hit points at the start of its turn"
            supp = regen.get('suppressed_by')
            if supp:
                line += f", but the healing is suppressed if it took {'/'.join(supp)} damage since its last turn"
            blocked = regen.get('blocked_by')
            if blocked:
                line += f" and is entirely blocked while {'/'.join(blocked)} apply"
            out.append(line)
        lr = legendary_resistance_max(entity)
        if lr:
            out.append(f"legendary resistance: when it fails a saving throw it "
                       f"can choose to succeed instead, {lr} times per day")
        if undead_fortitude_config(entity):
            out.append("undead fortitude: when reduced to 0 hit points it can "
                       "instead stay at 1 (radiant damage and regeneration-"
                       "blocking conditions deny this)")
        props = getattr(entity, 'properties', None) or {}
        if props.get('magic_resistance'):
            out.append("magic resistance: advantage on saving throws against "
                       "spells and other magical effects")
    except Exception:
        pass
    return out


def _effect_spell_props(effect_obj: Any) -> Optional[Dict[str, Any]]:
    return _props_dict(effect_obj)


def observed_rules_lines(battle: Any, entity: Any) -> List[str]:
    """Rules for spells/effects/traits currently visible on the battlefield.

    One line per distinct spell or trait, noting who it is on, so the
    strategist plans against what those rules actually do instead of
    imagining variants.
    """
    if battle is None or entity is None:
        return []
    # spell name -> {'desc': str, 'on': [who]}
    spells: Dict[str, Dict[str, Any]] = {}
    traits: List[tuple] = []  # (who, line)

    def add_spell(name: str, props: Dict[str, Any], who: str) -> None:
        entry = spells.setdefault(name, {'desc': spell_rules(props) or '', 'on': []})
        if who not in entry['on']:
            entry['on'].append(who)

    try:
        combatants = list(battle.entities.keys())
    except Exception:
        return []
    for other in combatants:
        if other is None:
            continue
        try:
            if getattr(other, 'dead', lambda: False)():
                continue
        except Exception:
            pass
        who = getattr(other, 'name', None) or str(other)
        for descs in (getattr(other, 'effects', None) or {}).values():
            for desc in (descs or []):
                props = _effect_spell_props(desc.get('effect'))
                if not props or not (props.get('description') or props.get('label')
                                     or props.get('name')):
                    continue
                name = str(props.get('label') or props.get('name') or '').strip()
                if name:
                    add_spell(name, props, who)
        for ce in (getattr(other, 'casted_effects', None) or []):
            props = _effect_spell_props(ce.get('effect') if isinstance(ce, dict) else ce)
            if not props or not (props.get('description') or props.get('label')
                                 or props.get('name')):
                continue
            name = str(props.get('label') or props.get('name') or '').strip()
            if name:
                add_spell(name, props, who)
        traits.extend((who, t) for t in _trait_lines(other))

    # Spells cast earlier in this battle (so the strategist knows the rules
    # of options it may counter, copy or avoid).
    try:
        log = list(getattr(battle, 'battle_log', None) or [])[-40:]
        for action in log:
            for item in (getattr(action, 'result', None) or []):
                if not isinstance(item, dict):
                    continue
                props = _effect_spell_props(item.get('spell'))
                if props and (props.get('description') or props.get('label')):
                    name = str(props.get('label') or props.get('name') or '').strip()
                    if name:
                        add_spell(name, props, getattr(item.get('source'), 'name', 'earlier'))
    except Exception:
        pass

    budget = _budget('N20_STRATEGIST_OBSERVED_CHARS', MAX_OBSERVED_BUDGET)
    out: List[str] = []
    used = 0
    for name, info in spells.items():
        if len(out) >= MAX_OBSERVED_ITEMS:
            break
        line = f"{name} (on {', '.join(info['on'][:4])}): {info['desc']}" \
            if info['desc'] else \
            f"{name} (on {', '.join(info['on'][:4])})"
        line = _cut(line)
        if used + len(line) > budget:
            break
        used += len(line)
        out.append(line)
    for who, line in traits:
        if len(out) >= MAX_OBSERVED_ITEMS:
            break
        full = _cut(f"{who} — {line}")
        if used + len(full) > budget:
            break
        used += len(full)
        out.append(full)
    return out[:MAX_OBSERVED_ITEMS]
