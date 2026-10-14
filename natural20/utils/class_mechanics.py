"""Generic class mechanics declared in class YAML.

Each block is a list of entries; an entry applies only while the character has
its ``feature``. Entries can live at the top of the class YAML or inside a
``subclasses.<name>`` block of a data-driven class (see
``natural20/entity_class/data_driven.py``).

``save_assists`` — reaction that adds an ability modifier to a saving throw
made by the character or a creature it can see nearby, when that turns a
failure into a success::

    save_assists:
      - feature: flash_of_genius
        ability: intelligence
        range: 30
        pool: flash_of_genius

``spell_roll_bonuses`` — add an ability modifier (min 1) to one damage or
healing roll of the character's spells::

    spell_roll_bonuses:
      - feature: alchemical_savant
        ability: intelligence
        min: 1
        damage_types: [acid, fire, necrotic, poison]
        healing: true
        requires_item: [alchemists_supplies]

``free_casts`` — cast a spell without a slot, spending a resource pool::

    free_casts:
      - feature: restorative_reagents
        spell: lesser_restoration
        pool: restorative_reagents
      - feature: spell_storing_item
        spell_property: spell_storing_item   # sheet key holding {spell: slug}
        pool: spell_storing_item
      - feature: mystic_arcanum
        spell_property: mystic_arcanum       # sheet key holding {6: summon_fiend}
        spell_key: 6
        pool: mystic_arcanum_6
      - feature: fiendish_vigor
        spell: false_life
        at_will: true                        # no pool, unlimited
        maximize: true                       # spell reads it via free_cast_spec_for
        self_only: true

``spell_source: spell_abilities`` with ``spell_level`` (and optional
``spell_index`` for the Nth matching spell) picks the spell from the sheet's
``spell_abilities`` map.

``rest_items`` — items produced after a rest (random or fixed)::

    rest_items:
      - feature: experimental_elixir
        id: experimental_elixir
        restore_on: long_rest
        count: {3: 1, 6: 2, 15: 3}           # class level -> count
        random_table: [elixir_of_healing, ...]
        expire_on_rest: true                 # unused ones vanish next rest

``craft_options`` — action that spends a spell slot to create an item
(``natural20/actions/craft_item_action.py``)::

    craft_options:
      - feature: experimental_elixir
        id: experimental_elixir
        label: Experimental Elixir
        items: [elixir_of_healing, ...]
        cost: spell_slot
        min_slot: 1
        requires_item: [alchemists_supplies]

``infusions`` — catalogue of item enhancements the sheet can apply through
``infusions: [{infusion: <key>, item: <inventory key>}]``::

    infusions:
      enhanced_defense:
        item_types: [armor, shield]
        magic_bonus: {2: 1, 10: 2}           # class level -> bonus

``initiative_bonuses`` / ``speed_bonuses`` / ``first_turn_movement`` /
``senses`` / ``feature_actions`` / ``rest_effects`` — initiative, walking
speed (``unless_armor``), first-turn movement, darkvision (plus
``evade_darkvision``), self-targeted pool actions
(``natural20/actions/class_feature_action.py``) and rest riders. See
``docs/CAMPAIGN_BUILDING.md`` → "Data-driven classes".
"""

from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.entity_class.data_driven import leveled_entries, normalize_ability

CRAFTED_BY_KEY = 'crafted_by'
REST_LEDGER_KEY = 'rest_granted_items'


def _has_feature(entity, feature):
    if not feature:
        return True
    try:
        return bool(entity.class_feature(feature))
    except Exception:
        return False


def class_specs(entity, key):
    """``(klass, spec)`` for every ``key`` entry whose feature the entity has."""
    class_props = getattr(entity, 'class_properties', None) or {}
    out = []
    for klass, props in class_props.items():
        blocks = [(props or {}).get(key) or []]
        sub_props = getattr(entity, 'data_class_subclass_props', None)
        if callable(sub_props):
            try:
                blocks.append((sub_props(klass) or {}).get(key) or [])
            except Exception:
                pass
        for block in blocks:
            if isinstance(block, dict):
                block = [dict(spec or {}, id=spec_id) if isinstance(spec, dict) else spec
                         for spec_id, spec in block.items()]
            for spec in block:
                if isinstance(spec, dict) and _has_feature(entity, spec.get('feature')):
                    out.append((klass, spec))
    return out


def _class_level(entity, klass):
    try:
        return int((entity.properties.get('classes') or {}).get(klass, 0) or 0)
    except Exception:
        return 0


def _level_table_value(table, level, default=0):
    if not isinstance(table, dict):
        try:
            return int(table)
        except (TypeError, ValueError):
            return default
    value = default
    for lvl, count in table.items():
        try:
            if int(level) >= int(lvl):
                value = int(count)
        except (TypeError, ValueError):
            continue
    return value


def _ability_bonus(entity, spec):
    ability = normalize_ability(spec.get('ability') or 'intelligence')
    bonus = int(entity.ability_mod(ability) or 0)
    if spec.get('min') is not None:
        bonus = max(int(spec['min']), bonus)
    return bonus


def _has_required_items(entity, spec):
    required = spec.get('requires_item')
    if not required:
        return True
    if isinstance(required, str):
        required = [required]
    return any(entity.item_count(item) > 0 for item in required)


# ---------------------------------------------------------------------------
# Prepared spells
# ---------------------------------------------------------------------------

def stored_spell(entity, spec):
    prop = spec.get('spell_property')
    if prop:
        value = (entity.properties or {}).get(prop)
        if isinstance(value, dict):
            key = spec.get('spell_key')
            if key is None:
                return value.get('spell')
            return value.get(key, value.get(str(key)))
        if value or not spec.get('spell_source'):
            return value
    if spec.get('spell_source') == 'spell_abilities':
        return _spell_from_abilities(entity, spec.get('spell_level'), spec.get('spell_list'),
                                     index=int(spec.get('spell_index') or 0))
    return spec.get('spell')


def _spell_from_abilities(entity, level, spell_list=None, index=0):
    """``index``-th spell of ``level`` (and on ``spell_list``, if given) in the
    sheet's ``spell_abilities`` map, which lists spells granted outside a class."""
    session = getattr(entity, 'session', None)
    for slug in ((entity.properties or {}).get('spell_abilities') or {}):
        try:
            details = session.load_spell(slug) if session is not None else None
        except Exception:
            details = None
        if not details:
            continue
        if level is not None and int(details.get('level', 0) or 0) != int(level):
            continue
        classes = [str(c).lower() for c in details.get('spell_list_classes') or []]
        if spell_list and classes and str(spell_list).lower() not in classes:
            continue
        if index > 0:
            index -= 1
            continue
        return slug
    return None


def free_cast_specs(entity):
    """``free_casts`` entries from class YAML and from feats (``feats/<id>.yml``)."""
    from natural20.utils.feat_mechanics import ensure_feat_pools, feat_specs
    specs = list(class_specs(entity, 'free_casts'))
    feat_entries = feat_specs(entity, 'free_casts')
    if feat_entries:
        ensure_feat_pools(entity)
        specs.extend(feat_entries)
    from natural20.utils.innate_spellcasting import innate_free_cast_specs
    specs.extend((None, spec) for spec in innate_free_cast_specs(entity))
    return specs


def extra_prepared_spells(entity):
    """Always-prepared spells: data-driven subclass spells, free-cast spells
    and race/subrace ``spells`` lists."""
    spells = []
    for klass in getattr(entity, 'yaml_subclass_classes', lambda: [])():
        spells.extend(entity.data_class_subclass_spells(klass))
    for _klass, spec in free_cast_specs(entity):
        slug = stored_spell(entity, spec)
        if slug:
            spells.append(slug)
    race_props = getattr(entity, 'race_properties', None) or {}
    spells.extend(race_props.get('spells') or [])
    subrace = entity.subrace() if callable(getattr(entity, 'subrace', None)) else None
    if subrace:
        spells.extend(((race_props.get('subrace') or {}).get(subrace) or {}).get('spells') or [])
    out = []
    session = getattr(entity, 'session', None)
    for spell in spells:
        if not spell or spell in out:
            continue
        try:
            known = session.load_spell(spell) if session is not None else None
        except Exception:
            known = None
        if known:
            out.append(spell)
    return out


# ---------------------------------------------------------------------------
# Free casts (no spell slot)
# ---------------------------------------------------------------------------

AT_WILL_POOL = 'at_will'


def _free_cast_usable(entity, spec):
    if spec.get('at_will'):
        return True
    pool = spec.get('pool')
    return bool(pool) and entity.has_resource(pool)


def free_cast_spec_for(entity, spell_slug, pool=None):
    """The usable ``free_casts`` entry for ``spell_slug`` (matching ``pool`` when given)."""
    if not spell_slug:
        return None
    for _klass, spec in free_cast_specs(entity):
        if stored_spell(entity, spec) != spell_slug or not _free_cast_usable(entity, spec):
            continue
        if pool is not None and (AT_WILL_POOL if spec.get('at_will') else spec.get('pool')) != pool:
            continue
        return spec
    return None


def free_cast_pool_for(entity, spell_slug):
    """Resource pool that pays for casting ``spell_slug`` without a slot, if any
    use is left. At-will entries return :data:`AT_WILL_POOL`; limited pools win."""
    if not spell_slug:
        return None
    at_will = False
    for _klass, spec in free_cast_specs(entity):
        if stored_spell(entity, spec) != spell_slug or not _free_cast_usable(entity, spec):
            continue
        if spec.get('at_will'):
            at_will = True
            continue
        return spec.get('pool')
    return AT_WILL_POOL if at_will else None


def spend_free_cast(caster, pool):
    """Pay for a free cast; True when the slot should not be spent."""
    if not pool:
        return False
    if pool == AT_WILL_POOL:
        return True
    return bool(caster.consume_resource(pool))


def free_cast_label(entity, spell_slug):
    """Short label for the free-cast button (``Free``, ``Free 2/3``)."""
    pool = free_cast_pool_for(entity, spell_slug)
    if pool is None:
        return None
    if pool == AT_WILL_POOL:
        return 'At will'
    res = entity.get_resource(pool) if hasattr(entity, 'get_resource') else None
    if res is None:
        return 'Free'
    return f"Free {res.current}/{res.max_value}"


# ---------------------------------------------------------------------------
# Spell roll bonuses
# ---------------------------------------------------------------------------

def apply_spell_roll_bonuses(entity, spell_props, items, battle=None):
    """Add the first matching ``spell_roll_bonuses`` entry to the spell's damage
    or healing rolls (once per target)."""
    if not items or entity is None:
        return items
    specs = class_specs(entity, 'spell_roll_bonuses')
    if not specs:
        return items
    for _klass, spec in specs:
        if not _has_required_items(entity, spec):
            continue
        damage_types = set(spec.get('damage_types') or [])
        bonus = _ability_bonus(entity, spec)
        if bonus <= 0:
            continue
        seen_targets = set()
        bonused = {}
        applied = False
        for item in items:
            if not isinstance(item, dict) or item.get('source') is not entity:
                continue
            target_key = id(item.get('target'))
            if target_key in seen_targets:
                continue
            kind = item.get('type')
            if kind == 'spell_damage' and item.get('damage_type') in damage_types and item.get('damage') is not None:
                field = 'damage'
            elif kind == 'spell_heal' and spec.get('healing') and item.get('heal_roll') is not None:
                field = 'heal_roll'
            else:
                continue
            roll = item[field]
            if id(roll) not in bonused:
                extra = DieRoll.roll(f"+{bonus}", description=f"spell_bonus:{spec.get('feature')}",
                                     entity=entity, battle=battle)
                bonused[id(roll)] = roll + extra
            item[field] = bonused[id(roll)]
            if field == 'damage' and item.get('damage_roll') is not None:
                item['damage_roll'] = item['damage']
            item.setdefault('roll_bonuses', []).append(spec.get('feature'))
            seen_targets.add(target_key)
            applied = True
        if applied:
            break
    return items


# ---------------------------------------------------------------------------
# Save assists (reaction)
# ---------------------------------------------------------------------------

def _can_react(helper, battle):
    if battle is None or not helper.conscious():
        return False
    try:
        if helper.incapacitated():
            return False
    except Exception:
        pass
    if battle.entity_state_for(helper) is None:
        return False
    return helper.has_reaction(battle)


def _is_ally(battle, helper, creature):
    if helper is creature:
        return True
    try:
        return bool(battle.allies(helper, creature))
    except Exception:
        return getattr(helper, 'group', None) == getattr(creature, 'group', None)


def _within_sight(battle, helper, creature, range_ft):
    if helper is creature:
        return True
    battle_map = battle.map_for(helper)
    if battle_map is None or battle_map is not battle.map_for(creature):
        return False
    try:
        if battle_map.distance(helper, creature) * battle_map.feet_per_grid > range_ft:
            return False
        return bool(battle.can_see(helper, creature))
    except Exception:
        return False


def _ask(helper, battle, event):
    """Ask the helper's controller; interactive controllers use it automatically."""
    from natural20.utils.giant_ancestry import _ask_controller
    from natural20.action import Action

    class _SaveAssistOption(Action):
        def __init__(self):
            super().__init__(helper.session, helper, event['feature'])

        def label(self):
            return str(event['feature']).replace('_', ' ').title()

        def __str__(self):
            return self.label()

    option = _SaveAssistOption()
    return _ask_controller(helper, battle, [option], event) is not None


def try_save_assist(creature, save_roll, dc, save_type, battle=None):
    """Offer ``save_assists`` reactions to helpers when ``save_roll`` misses ``dc``."""
    if battle is None or dc is None:
        return save_roll
    try:
        total = int(save_roll.result())
        dc = int(dc)
    except Exception:
        return save_roll
    if total >= dc:
        return save_roll
    for helper in list(getattr(battle, 'entities', {}).keys()):
        if not hasattr(helper, 'class_properties'):
            continue
        for _klass, spec in class_specs(helper, 'save_assists'):
            pool = spec.get('pool')
            if pool and not helper.has_resource(pool):
                continue
            if not _can_react(helper, battle) or not _is_ally(battle, helper, creature):
                continue
            if not _within_sight(battle, helper, creature, int(spec.get('range', 30))):
                continue
            bonus = _ability_bonus(helper, spec)
            if bonus <= 0 or total + bonus < dc:
                continue
            event = {
                'type': 'save_assist', 'feature': spec.get('feature'),
                'trigger': 'saving_throw', 'source': helper, 'target': creature,
                'save_type': save_type, 'dc': dc, 'roll': total, 'bonus': bonus,
            }
            if not _ask(helper, battle, event):
                continue
            battle.consume(helper, 'reaction')
            if pool:
                helper.consume_resource(pool)
            save_roll = save_roll + DieRoll.roll(
                f"+{bonus}", description=f"save_modifier:{spec.get('feature')}",
                entity=helper, battle=battle)
            helper.session.event_manager.received_event({
                'event': 'save_assist', 'source': helper, 'target': creature,
                'feature': spec.get('feature'), 'bonus': bonus,
                'save_type': save_type, 'roll': save_roll, 'dc': dc,
            })
            return save_roll
    return save_roll


# ---------------------------------------------------------------------------
# Rest items and crafting
# ---------------------------------------------------------------------------

def _ledger(entity):
    return entity.properties.setdefault(REST_LEDGER_KEY, {})


def record_crafted_item(entity, ledger_key, item):
    if ledger_key:
        _ledger(entity).setdefault(ledger_key, []).append(item)


def give_crafted_item(entity, item, ledger_key=None):
    entity.add_item(item, 1, source_item={'type': item, 'qty': 1, CRAFTED_BY_KEY: entity.entity_uid})
    record_crafted_item(entity, ledger_key, item)


def _expire_ledger(entity, ledger_key):
    for item in _ledger(entity).pop(ledger_key, []) or []:
        if entity.item_count(item) > 0:
            entity.deduct_item(item, 1)


def grant_rest_items(entity, klass, rest_kind):
    granted = []
    for spec_class, spec in class_specs(entity, 'rest_items'):
        if spec_class != klass or spec.get('restore_on', 'long_rest') != rest_kind:
            continue
        ledger_key = spec.get('id') or spec.get('feature')
        if spec.get('expire_on_rest', True):
            _expire_ledger(entity, ledger_key)
        count = _level_table_value(spec.get('count', 1), _class_level(entity, klass), default=0)
        table = list(spec.get('random_table') or spec.get('items') or [])
        if not table:
            continue
        for _ in range(count):
            if spec.get('random_table'):
                roll = DieRoll.roll(f"1d{len(table)}", description=f"dice_roll.{ledger_key}", entity=entity)
                item = table[roll.result() - 1]
            else:
                item = table[len(granted) % len(table)]
            give_crafted_item(entity, item, ledger_key)
            granted.append(item)
        if granted:
            entity.session.event_manager.received_event({
                'event': 'rest_items', 'source': entity, 'feature': spec.get('feature'),
                'items': list(granted),
            })
    return granted


def crafted_by(entity, inventory_key):
    """UID of the creature that crafted the stack ``inventory_key`` (``None`` if unknown)."""
    entry = (getattr(entity, 'inventory', None) or {}).get(inventory_key) or {}
    return entry.get(CRAFTED_BY_KEY)


# ---------------------------------------------------------------------------
# Infusions (item enhancements)
# ---------------------------------------------------------------------------

def item_enhancements(entity):
    """``{item_key: {'magic_bonus': n}}`` from the sheet's ``infusions`` list."""
    infusions = (getattr(entity, 'properties', None) or {}).get('infusions') or []
    if not infusions:
        return {}
    catalog = {}
    for klass, spec in class_specs(entity, 'infusions'):
        catalog[spec.get('id')] = (klass, spec)
    out = {}
    for entry in infusions:
        if not isinstance(entry, dict):
            continue
        found = catalog.get(entry.get('infusion'))
        item = entry.get('item')
        if not found or not item:
            continue
        klass, spec = found
        bonus = _level_table_value(spec.get('magic_bonus', 0), _class_level(entity, klass), default=0)
        enhancement = out.setdefault(item, {'magic_bonus': 0, 'infusions': []})
        enhancement['magic_bonus'] += bonus
        enhancement['infusions'].append(entry.get('infusion'))
    return out


def _item_keys(item_meta):
    keys = {item_meta.get('id'), item_meta.get('_inventory_key')}
    name = item_meta.get('name')
    if name:
        keys.add(str(name).lower().replace(' ', '_'))
    return {k for k in keys if k}


def effect_enhancement_bonus(entity, item_meta):
    """Bonus from ``item_enhancement`` effects on ``entity`` (e.g. Magic Weapon).

    The handler receives ``opts['item_keys']`` (id / inventory key / slug of the
    item) and returns the accumulated ``value`` plus its own bonus when it
    enhances that item."""
    if not item_meta or entity is None or not hasattr(entity, 'has_effect'):
        return 0
    try:
        if not entity.has_effect('item_enhancement'):
            return 0
        return int(entity.eval_effect('item_enhancement', {
            'stacked': True, 'value': 0, 'item_keys': _item_keys(item_meta), 'item': item_meta,
        }) or 0)
    except Exception:
        return 0


def enhancement_bonus(entity, item_meta):
    """Extra ``magic_bonus`` an infusion (or an ``item_enhancement`` effect)
    grants the item described by ``item_meta``."""
    if not item_meta:
        return 0
    bonus = effect_enhancement_bonus(entity, item_meta)
    enhancements = item_enhancements(entity)
    if not enhancements:
        return bonus
    for key in _item_keys(item_meta):
        if key in enhancements:
            return bonus + int(enhancements[key].get('magic_bonus', 0) or 0)
    return bonus


# ---------------------------------------------------------------------------
# Initiative, speed and senses
# ---------------------------------------------------------------------------

def spec_value(entity, spec, klass=None, key='bonus'):
    """Resolve a numeric YAML value: int, ``proficiency_bonus``,
    ``ability_mod:<ab>`` or a ``{class level: n}`` table (``min`` honoured)."""
    from natural20.entity_class.data_driven import resolve_pool_max
    if spec.get(key) is None:
        return 0
    return resolve_pool_max(entity, {'max': spec.get(key), 'min': spec.get('min')},
                            _class_level(entity, klass) if klass else 0)


def class_initiative_bonus(entity):
    """``initiative_bonuses``: added to initiative rolls (e.g. ``bonus: ability_mod:wisdom``)."""
    return sum(spec_value(entity, spec, klass) for klass, spec in class_specs(entity, 'initiative_bonuses'))


def _armor_subtypes(entity):
    try:
        return {str(item.get('subtype') or '') for item in entity.equipped_armor() if item.get('type') == 'armor'}
    except Exception:
        return set()


def class_speed_bonus(entity):
    """``speed_bonuses``: walking speed bonus, optionally lost in some armor
    (``unless_armor: [heavy]``)."""
    total = 0
    for klass, spec in class_specs(entity, 'speed_bonuses'):
        blocked = set(spec.get('unless_armor') or [])
        if blocked and blocked & _armor_subtypes(entity):
            continue
        total += spec_value(entity, spec, klass, key='amount')
    return total


def class_darkvision(entity, base=0):
    """``senses``: ``darkvision: 60`` (or ``darkvision_extend: 60`` added when
    the creature already has darkvision)."""
    best = int(base or 0)
    for klass, spec in class_specs(entity, 'senses'):
        dv = spec_value(entity, spec, klass, key='darkvision')
        if base and spec.get('darkvision_extend'):
            dv = max(dv, int(base) + spec_value(entity, spec, klass, key='darkvision_extend'))
        best = max(best, dv)
    return best


def cantrip_rider_specs(entity, spell_slug):
    """``cantrip_riders`` entries that apply to ``spell_slug``::

        cantrip_riders:
          - feature: agonizing_blast
            spell_property: invocation_spells   # sheet {agonizing_blast: eldritch_blast}
            default_spell: eldritch_blast
            damage_bonus: ability_mod:charisma
          - feature: repelling_blast
            spell_property: invocation_spells
            default_spell: eldritch_blast
            push: 10                            # feet, on a hit
            max_size: large
    """
    out = []
    props = getattr(entity, 'properties', None) or {}
    for klass, spec in class_specs(entity, 'cantrip_riders'):
        chosen = None
        prop = spec.get('spell_property')
        if prop:
            value = props.get(prop)
            if isinstance(value, dict):
                chosen = value.get(spec.get('feature')) or value.get(spec.get('id'))
            elif isinstance(value, str):
                chosen = value
        chosen = chosen or spec.get('default_spell')
        if chosen == spell_slug:
            out.append((klass, spec))
    return out


def cantrip_damage_bonus(entity, spell_slug):
    return sum(spec_value(entity, spec, klass, key='damage_bonus')
               for klass, spec in cantrip_rider_specs(entity, spell_slug))


_SIZE_ORDER = ['tiny', 'small', 'medium', 'large', 'huge', 'gargantuan']


def cantrip_push(entity, spell_slug, target):
    """Feet ``target`` is pushed away on a hit with ``spell_slug`` (0 = none)."""
    best = 0
    for _klass, spec in cantrip_rider_specs(entity, spell_slug):
        feet = int(spec.get('push') or 0)
        if not feet:
            continue
        max_size = spec.get('max_size')
        if max_size and target is not None:
            try:
                size = str(target.size()).lower()
                if _SIZE_ORDER.index(size) > _SIZE_ORDER.index(str(max_size).lower()):
                    continue
            except (ValueError, AttributeError):
                pass
        best = max(best, feet)
    return best


def class_condition_immunities(entity):
    """``condition_immunities: [{feature: beguiling_defenses, conditions: [charmed]}]``."""
    out = []
    try:
        specs = class_specs(entity, 'condition_immunities')
    except Exception:
        return out
    for _klass, spec in specs:
        out.extend(spec.get('conditions') or [])
    return out


def devils_sight_range(entity):
    """Feet within which the creature sees normally in dim light and in
    magical or nonmagical darkness: ``senses: {devils_sight: 120}`` (class or
    feat YAML) or a top-level ``devils_sight: 120`` on NPC YAML."""
    props = getattr(entity, 'properties', None) or {}
    cache_key = (repr(props.get('classes')), tuple(props.get('feats') or ()),
                 tuple(props.get('eldritch_invocations') or ()), props.get('devils_sight'))
    cached = getattr(entity, '_devils_sight_cache', None)
    if cached is not None and cached[0] == cache_key:
        return cached[1]
    best = _devils_sight_uncached(entity)
    try:
        entity._devils_sight_cache = (cache_key, best)
    except Exception:
        pass
    return best


def _devils_sight_uncached(entity):
    best = 0
    try:
        best = int(((getattr(entity, 'properties', None) or {}).get('devils_sight')) or 0)
    except (TypeError, ValueError):
        best = 0
    try:
        specs = list(class_specs(entity, 'senses'))
    except Exception:
        specs = []
    try:
        from natural20.utils.feat_mechanics import feat_specs
        specs.extend(feat_specs(entity, 'senses'))
    except Exception:
        pass
    for klass, spec in specs:
        if spec.get('devils_sight'):
            best = max(best, spec_value(entity, spec, klass, key='devils_sight'))
    return best


def evades_darkvision(entity):
    """``senses: {evade_darkvision: true}`` hides the creature from sight that
    relies on darkvision while it stands in darkness (Umbral Sight style)."""
    return any(spec.get('evade_darkvision') for _k, spec in class_specs(entity, 'senses'))


def first_turn_movement_bonus(entity):
    """``first_turn_movement``: extra movement on the creature's first turn of a combat."""
    return sum(spec_value(entity, spec, klass, key='amount')
               for klass, spec in class_specs(entity, 'first_turn_movement'))


def apply_rest_effects(entity, rest_kind):
    """``rest_effects``: ``{rest: short_rest, reduce_exhaustion: 1}``."""
    for _klass, spec in class_specs(entity, 'rest_effects'):
        if (spec.get('rest') or 'long_rest') != rest_kind:
            continue
        reduce = int(spec.get('reduce_exhaustion') or 0)
        if reduce and callable(getattr(entity, 'exhaustion_level', None)):
            level = entity.exhaustion_level()
            if level:
                entity.set_exhaustion_level(max(0, level - reduce))
