"""YAML-driven weapon attack options granted by feats (or any creature).

Feat YAML (``feats/<id>.yml``) or creature YAML may list ``attack_options``::

    attack_options:
      - id: precise_strike             # also the resource-pool name
        name: Precise Strike
        timing: before_attack          # free toggle before rolling
        advantage: true                # advantage on that weapon attack roll
        extra_damage: 1d8              # added on a hit (weapon damage type)
        uses: proficiency_bonus        # or an integer
        recharge: long_rest            # long_rest | short_rest
        expend: on_hit                 # on_hit (default for before_attack) | on_use
        once_per_turn: true

      - id: demoralizing_strike
        name: Demoralizing Strike
        timing: on_hit                 # offered right after a weapon hit
        uses: proficiency_bonus
        recharge: long_rest
        once_per_turn: true
        save:
          ability: wisdom
          dc_abilities: [int, wis, cha]   # DC 8 + PB + best of these modifiers
        on_fail:
          condition: frightened        # source-linked (see natural20/utils/fear.py)
          rounds: 1                    # lasts until the end of the user's next turn
        on_success:
          next_attack_disadvantage: true

Class YAML can declare the same ``attack_options`` list (gated by
``feature``, top level or under ``subclasses.<name>``). Extra keys:

* ``pool`` — resource-pool name shared by several options (default: ``id``);
  ``uses`` also accepts ``ability_mod:<ability>`` with ``min_uses``.
* ``extra_damage`` as a class-level table (``{3: 2d6, 11: 2d8}``) and
  ``damage_type`` (e.g. ``psychic``).
* ``variants`` — alternative versions offered alongside the base option
  (same pool and once-per-turn slot). Each may add ``feature`` (gate),
  ``save`` (with ``radius`` to also affect creatures near the target),
  ``on_fail`` / ``on_success`` and ``follow_up_attack: {range: 5}`` (a free
  attack with the same weapon on another creature within ``range`` feet of
  the target, see ``natural20/actions/granted_attack_action.py``).
* ``rounds: 0`` on a branch lasts until the start of the user's next turn.

Before-attack options surface as ``AttackOptionAction`` (no action cost);
on-hit options are offered through ``controller.select_reaction`` by
``AttackOptionHitOffer`` (an ``on_attack_hit`` hook installed on load).
"""

from __future__ import annotations

from natural20.die_roll import DieRoll

ROUND_SECONDS = 6
_ABILITY_NAMES = {
    'str': 'strength', 'dex': 'dexterity', 'con': 'constitution',
    'int': 'intelligence', 'wis': 'wisdom', 'cha': 'charisma',
}


def _feat_definition(session, feat_id):
    cache = getattr(session, '_feat_definition_cache', None)
    if cache is None:
        cache = {}
        try:
            session._feat_definition_cache = cache
        except Exception:
            pass
    if feat_id in cache:
        return cache[feat_id]
    data = None
    try:
        from natural20.yaml_loader import load_campaign_resource_path
        loaded = load_campaign_resource_path(session.root_path, f"feats/{feat_id}.yml")
        if isinstance(loaded, dict):
            data = loaded.get(feat_id, loaded)
    except Exception:
        data = None
    cache[feat_id] = data
    return data


def attack_options_for(entity):
    props = getattr(entity, 'properties', None) or {}
    options = []
    session = getattr(entity, 'session', None)
    for feat in props.get('feats') or []:
        definition = _feat_definition(session, str(feat)) if session is not None else None
        for opt in (definition or {}).get('attack_options') or []:
            if isinstance(opt, dict) and opt.get('id'):
                options.append(dict(opt, feat=str(feat)))
    for opt in props.get('attack_options') or []:
        if isinstance(opt, dict) and opt.get('id'):
            options.append(dict(opt))
    try:
        from natural20.utils.class_mechanics import class_specs
        for klass, opt in class_specs(entity, 'attack_options'):
            if opt.get('id'):
                options.append(dict(opt, klass=klass))
    except Exception:
        pass
    return options


def option_variants(entity, option):
    """Variants of ``option`` the entity can use, each sharing its pool and turn slot."""
    out = []
    for variant in option.get('variants') or []:
        if not isinstance(variant, dict) or not variant.get('id'):
            continue
        feature = variant.get('feature')
        if feature and not entity.class_feature(feature):
            continue
        merged = {k: v for k, v in option.items() if k != 'variants'}
        merged.update(variant)
        merged['pool'] = option.get('pool') or option['id']
        merged['turn_key'] = option.get('turn_key') or option['id']
        merged['uses'] = option.get('uses', 1)
        out.append(merged)
    return out


def _class_level(entity, option):
    klass = option.get('klass')
    try:
        if klass:
            return int((entity.properties.get('classes') or {}).get(klass, 0) or 0)
        return int(entity.level() or 0)
    except Exception:
        return 0


def option_extra_damage(entity, option):
    """``extra_damage`` dice, resolving a ``{class level: dice}`` table."""
    raw = option.get('extra_damage')
    if not isinstance(raw, dict):
        return raw
    level = _class_level(entity, option)
    value = None
    for lvl, dice in sorted(raw.items(), key=lambda kv: int(kv[0])):
        if level >= int(lvl):
            value = dice
    return value


def option_max_uses(entity, option):
    uses = option.get('uses', 1)
    if uses == 'proficiency_bonus':
        return int(entity.proficiency_bonus() or 0)
    if isinstance(uses, str) and uses.startswith('ability_mod:'):
        from natural20.entity_class.data_driven import resolve_pool_max
        return resolve_pool_max(entity, {'max': uses, 'min': option.get('min_uses', 1)})
    try:
        return int(uses)
    except (TypeError, ValueError):
        return 1


def option_pool(entity, option):
    name = option.get('pool') or option['id']
    pool = entity.get_resource(name)
    if pool is None:
        pool = entity.register_resource(name, option_max_uses(entity, option),
                                        restore_on=option.get('recharge', 'long_rest'))
    return pool


def _turn_marker(battle):
    return [getattr(battle, 'round', 0), getattr(battle, 'current_turn_index', 0)]


def used_this_turn(entity, battle, option):
    if battle is None or not option.get('once_per_turn', True):
        return False
    state = battle.entity_state_for(entity) or {}
    record = state.get('attack_options_used') or {}
    key = option.get('turn_key') or option['id']
    return record.get('turn') == _turn_marker(battle) and key in (record.get('ids') or [])


def mark_used(entity, battle, option):
    if battle is None:
        return
    state = battle.entity_state_for(entity)
    if state is None:
        return
    record = state.get('attack_options_used') or {}
    if record.get('turn') != _turn_marker(battle):
        record = {'turn': _turn_marker(battle), 'ids': []}
    record['ids'] = list(record.get('ids') or []) + [option.get('turn_key') or option['id']]
    state['attack_options_used'] = record


def option_available(entity, battle, option):
    pool = option_pool(entity, option)
    return pool.available(1) and not used_this_turn(entity, battle, option)


def is_weapon_hit(entity, hit_result):
    weapon_key = hit_result.get('weapon')
    if not weapon_key or hit_result.get('npc_action'):
        return bool(hit_result.get('npc_action'))
    weapon = entity.session.load_weapon(weapon_key) if isinstance(weapon_key, str) else weapon_key
    return isinstance(weapon, dict) and weapon.get('type') in ('melee_attack', 'ranged_attack')


def option_save_dc(entity, option):
    save = option.get('save') or {}
    mods = []
    for ability in save.get('dc_abilities') or ['str']:
        try:
            mods.append(int(entity.ability_mod(_ABILITY_NAMES.get(ability, ability)) or 0))
        except Exception:
            continue
    return 8 + int(entity.proficiency_bonus() or 0) + (max(mods) if mods else 0)


def extra_damage_item(entity, hit_result, option):
    attack_roll = hit_result.get('attack_roll')
    crit = bool(hit_result.get('critical') or (attack_roll is not None and attack_roll.nat_20()))
    damage = DieRoll.roll(str(option_extra_damage(entity, option)), crit=crit, entity=entity,
                          battle=hit_result.get('battle'),
                          description=f"dice_roll.{option['id']}")
    return {
        'type': 'additional_damage',
        'source': entity,
        'target': hit_result.get('target'),
        'battle': hit_result.get('battle'),
        'attack_name': option.get('name') or option['id'],
        'damage_type': option.get('damage_type') or hit_result.get('damage_type') or 'bludgeoning',
        'damage': damage,
        'life_drain': False,
        'critical': crit,
        'weapon': hit_result.get('weapon'),
        '_hit_state': hit_result.setdefault('_hit_state', {}),
    }


class AttackOptionEffect:
    """Pending before-attack option: advantage on the next weapon attack roll."""

    def __init__(self, source, option):
        self.source = source
        self.target = source
        self.action = None
        self.option = dict(option)
        self.rolled = False
        self.id = f"attack_option:{option['id']}:{id(self)}"

    def __str__(self):
        return str(self.option['id'])

    @staticmethod
    def attack_advantage_modifier(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None or effect.rolled or not effect.option.get('advantage'):
            return [[], []]
        return [[str(effect)], []]

    @staticmethod
    def attack_resolved(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is not None:
            effect.rolled = True
        return []

    @staticmethod
    def on_attack_hit(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        hit_result = opt.get('result') or {}
        if effect is None or not hit_result.get('hit?') or not is_weapon_hit(entity, hit_result):
            return []
        option = effect.option
        battle = hit_result.get('battle')
        results = []
        pool = option_pool(entity, option)
        if option.get('expend', 'on_hit') == 'on_hit':
            pool.consume(1)
        mark_used(entity, battle, option)
        if option.get('extra_damage'):
            results.append(extra_damage_item(entity, hit_result, option))
        entity.dismiss_effect(effect)
        return results

    @staticmethod
    def end_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is not None:
            entity.dismiss_effect(effect)
        return []


def pending_option_effect(entity, option_id=None):
    for entry in (getattr(entity, 'effects', None) or {}).get('attack_advantage_modifier', []) or []:
        effect = entry.get('effect')
        if isinstance(effect, AttackOptionEffect) and not effect.rolled and (
                option_id is None or effect.option['id'] == option_id):
            return effect
    return None


def activate_before_attack_option(entity, battle, option):
    """Arm a before-attack option (replacing a spent, missed one)."""
    for entry in list((getattr(entity, 'effects', None) or {}).get('attack_advantage_modifier', []) or []):
        effect = entry.get('effect')
        if isinstance(effect, AttackOptionEffect) and effect.option['id'] == option['id']:
            entity.dismiss_effect(effect)
    effect = AttackOptionEffect(entity, option)
    entity.register_effect('attack_advantage_modifier', AttackOptionEffect, effect=effect,
                           source=entity, duration=ROUND_SECONDS)
    for hook in ('attack_resolved', 'on_attack_hit', 'end_of_turn'):
        entity.register_event_hook(hook, AttackOptionEffect, hook, effect=effect,
                                   source=entity, duration=ROUND_SECONDS)
    if option.get('expend') == 'on_use':
        option_pool(entity, option).consume(1)
        mark_used(entity, battle, option)
    return effect
