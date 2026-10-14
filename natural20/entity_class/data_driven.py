"""YAML-driven character classes.

Classes shipped as data (e.g. from an expansion pack) need no Python mixin:
``PlayerCharacter`` falls back to :class:`DataDrivenClass` when there is no
``initialize_<klass>`` method. Everything comes from the class YAML::

    hit_die: 1d8
    spellcasting:
      ability: intelligence
      progression: half_round_up   # full | half | half_round_up | third
      # slot_table: [[2], [2], [3], ...]   # explicit per-level rows instead
    spell_list:                   # spells this class can cast with its slots
      level_0: [...]
      level_1: [...]
    progression:
      level_2: {class_features: [...]}
    subclass_property: my_subclass_key  # sheet key holding the subclass
    subclasses:
      some_subclass:
        features: {level_3: [...]}
        spells: {level_3: [...]}         # always prepared, count as class spells
    resource_pools:
      some_pool:
        max: ability_mod:intelligence    # int | proficiency_bonus | ability_mod:<ab> | {level: n}
        multiplier: 2                    # optional
        min: 1
        restore_on: long_rest
        feature: some_feature            # pool only exists with this feature

Generic class mechanics declared in the same YAML (``save_assists``,
``spell_roll_bonuses``, ``free_casts``, ``rest_items``, ``craft_options``,
``infusions``) are implemented in ``natural20/utils/class_mechanics.py``.
"""

from __future__ import annotations

import math
from collections import OrderedDict

FULL_CASTER_SLOTS = [
    [],
    [2],
    [3],
    [4, 2],
    [4, 3],
    [4, 3, 2],
    [4, 3, 3],
    [4, 3, 3, 1],
    [4, 3, 3, 2],
    [4, 3, 3, 3, 1],
    [4, 3, 3, 3, 2],
    [4, 3, 3, 3, 2, 1],
    [4, 3, 3, 3, 2, 1],
    [4, 3, 3, 3, 2, 1, 1],
    [4, 3, 3, 3, 2, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 2, 1, 1],
]

ABILITY_ALIASES = {
    'str': 'strength', 'dex': 'dexterity', 'con': 'constitution',
    'int': 'intelligence', 'wis': 'wisdom', 'cha': 'charisma',
}


def normalize_ability(ability):
    key = str(ability or '').strip().lower()
    return ABILITY_ALIASES.get(key, key)


def caster_level_for(progression, level):
    """Effective full-caster level used to read :data:`FULL_CASTER_SLOTS`."""
    level = int(level or 0)
    if level <= 0:
        return 0
    progression = str(progression or 'none').lower()
    if progression == 'full':
        return level
    if progression == 'half':
        return level // 2 if level >= 2 else 0
    if progression == 'half_round_up':
        return int(math.ceil(level / 2))
    if progression == 'third':
        return level // 3 if level >= 3 else 0
    return 0


def slot_row(class_props, level):
    """Spell slot counts ``[1st, 2nd, ...]`` for a data-driven class level."""
    spellcasting = (class_props or {}).get('spellcasting') or {}
    table = spellcasting.get('slot_table')
    level = int(level or 0)
    if table:
        if level <= 0:
            return []
        row = table[min(level, len(table)) - 1] or []
        return [int(n) for n in row]
    caster_level = caster_level_for(spellcasting.get('progression'), level)
    return list(FULL_CASTER_SLOTS[min(caster_level, 20)])


def leveled_entries(table, level):
    """Flatten a ``{level_N: [...]}`` table up to ``level`` (inclusive)."""
    out = []
    for key, values in (table or {}).items():
        try:
            required = int(str(key).split('_')[-1])
        except (TypeError, ValueError):
            continue
        if required > int(level or 0):
            continue
        for value in values or []:
            if value not in out:
                out.append(value)
    return out


def resolve_pool_max(entity, spec, class_level=None):
    raw = spec.get('max', 1)
    value = 0
    if isinstance(raw, dict):
        for lvl, count in raw.items():
            try:
                if int(class_level or 0) >= int(lvl):
                    value = max(value, int(count))
            except (TypeError, ValueError):
                continue
    elif raw == 'proficiency_bonus':
        value = int(entity.proficiency_bonus())
    elif isinstance(raw, str) and raw.startswith('ability_mod:'):
        value = int(entity.ability_mod(normalize_ability(raw.split(':', 1)[1])) or 0)
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 1
    value *= int(spec.get('multiplier', 1) or 1)
    if spec.get('min') is not None:
        value = max(int(spec['min']), value)
    return max(0, value)


class DataDrivenClass:
    """Fallback class behaviour for YAML-only classes (mixed into ``PlayerCharacter``)."""

    def is_data_driven_class(self, klass):
        return (
            getattr(self, f"initialize_{klass}", None) is None
            and klass in (getattr(self, 'class_properties', None) or {})
        )

    def data_driven_classes(self):
        return [k for k in (getattr(self, 'class_properties', None) or {}) if self.is_data_driven_class(k)]

    def data_class_level(self, klass):
        return int((self.properties.get('classes') or {}).get(klass, 0) or 0)

    def data_class_subclass(self, klass):
        props = self.class_properties.get(klass) or {}
        field = props.get('subclass_property')
        if not field:
            return None
        return self.properties.get(field)

    def data_class_subclass_props(self, klass):
        sub = self.data_class_subclass(klass)
        if not sub:
            return {}
        return ((self.class_properties.get(klass) or {}).get('subclasses') or {}).get(sub) or {}

    def initialize_data_driven_class(self, klass):
        props = self.class_properties.get(klass) or {}
        if props.get('spellcasting'):
            self.spell_slots[klass] = self.reset_data_class_spell_slots(klass)
        self._register_data_class_pools(klass)

    def _register_data_class_pools(self, klass):
        level = self.data_class_level(klass)
        pools = dict((self.class_properties.get(klass) or {}).get('resource_pools') or {})
        pools.update(self.data_class_subclass_props(klass).get('resource_pools') or {})
        for name, spec in pools.items():
            if not isinstance(spec, dict):
                continue
            feature = spec.get('feature')
            if feature and not self.class_feature(feature):
                continue
            new_max = resolve_pool_max(self, spec, level)
            restore_on = spec.get('restore_on', 'long_rest')
            existing = self.get_resource(name)
            if existing is None:
                self.register_resource(name, new_max, restore_on=restore_on)
            else:
                gained = max(0, new_max - existing.max_value)
                self.register_resource(name, new_max, restore_on=restore_on,
                                       current=min(new_max, existing.current + gained))

    # -- spell slots ---------------------------------------------------------

    def reset_data_class_spell_slots(self, klass):
        row = slot_row(self.class_properties.get(klass), self.data_class_level(klass))
        slots = OrderedDict([(0, 0)])
        for index, count in enumerate(row):
            slots[index + 1] = count
        return slots

    def max_slots_for_data_class(self, klass, level):
        row = slot_row(self.class_properties.get(klass), self.data_class_level(klass))
        if level <= 0 or level > len(row):
            return 0
        return row[level - 1]

    def data_class_spellcasting_ability(self, klass):
        props = self.class_properties.get(klass) or {}
        ability = (props.get('spellcasting') or {}).get('ability') or props.get('spellcasting_ability')
        return normalize_ability(ability) if ability else None

    def data_class_spell_attack_modifier(self, klass):
        ability = self.data_class_spellcasting_ability(klass)
        if not ability:
            return 0
        return self.proficiency_bonus() + self.ability_mod(ability)

    # -- spell lists ---------------------------------------------------------

    def data_class_spell_list(self, klass):
        props = self.class_properties.get(klass) or {}
        spells = set()
        for values in (props.get('spell_list') or {}).values():
            spells.update(values or [])
        spells.update(self.data_class_subclass_spells(klass))
        return spells

    def data_class_subclass_spells(self, klass):
        sub = self.data_class_subclass_props(klass)
        return leveled_entries(sub.get('spells'), self.data_class_level(klass))

    def yaml_subclass_classes(self):
        """Classes (mixin or data-driven) whose YAML declares ``subclass_property`` + ``subclasses``."""
        out = []
        for klass, props in (getattr(self, 'class_properties', None) or {}).items():
            if (props or {}).get('subclass_property') and (props or {}).get('subclasses'):
                out.append(klass)
        return out

    def data_class_has_feature(self, feature):
        for klass in self.yaml_subclass_classes():
            sub = self.data_class_subclass_props(klass)
            if feature in leveled_entries(sub.get('features'), self.data_class_level(klass)):
                return True
        return False

    # -- rests ----------------------------------------------------------------

    def long_rest_for_data_class(self, klass, battle=None):
        if (self.class_properties.get(klass) or {}).get('spellcasting'):
            self.spell_slots[klass] = self.reset_data_class_spell_slots(klass)
        from natural20.utils.class_mechanics import grant_rest_items
        grant_rest_items(self, klass, 'long_rest')
