"""Goliath giant ancestry boons and other limited-use racial traits.

Traits are plain feature keys (race ``race_features``, subrace features, or an
NPC's ``attributes``) so any race or monster can reuse them:

- ``fires_burn`` / ``frosts_chill`` / ``hills_tumble``: optional riders when the
  creature hits with an attack roll and deals damage (``on_attack_hit`` hook).
- ``stones_endurance``: reaction that reduces incoming damage before it is
  applied (called from ``Entity.take_damage``).
- ``storms_thunder``: reaction that strikes back at a creature within 60 ft
  that damaged the creature (called from ``after_take_damage_hook``).
- ``clouds_jaunt`` / ``large_form``: bonus actions
  (``natural20/actions/clouds_jaunt_action.py``, ``large_form_action.py``).
- ``powerful_build``: advantage on checks to escape a grapple; carrying
  capacity as one size larger.

Uses come from ``ResourcePool`` entries declared in race YAML
``resource_pools`` (top level and per subrace; subrace entries win)::

    resource_pools:
      giant_ancestry:
        max: proficiency_bonus      # or an integer
        restore_on: long_rest       # short_rest | long_rest
        features: [fires_burn, stones_endurance, ...]

NPCs can declare the same block at the top level of their YAML.
"""

from __future__ import annotations

from natural20.action import Action, AsyncReactionHandler
from natural20.die_roll import DieRoll


ANCESTRY_FEATURES = (
    'clouds_jaunt', 'fires_burn', 'frosts_chill',
    'hills_tumble', 'stones_endurance', 'storms_thunder',
)
ON_HIT_FEATURES = ('fires_burn', 'frosts_chill', 'hills_tumble')
POOL_FEATURES = ANCESTRY_FEATURES + ('large_form',)

FEATURE_LABELS = {
    'clouds_jaunt': "Cloud's Jaunt",
    'fires_burn': "Fire's Burn",
    'frosts_chill': "Frost's Chill",
    'hills_tumble': "Hill's Tumble",
    'stones_endurance': "Stone's Endurance",
    'storms_thunder': "Storm's Thunder",
    'large_form': 'Large Form',
    'powerful_build': 'Powerful Build',
}

ON_HIT_DAMAGE = {
    'fires_burn': ('1d10', 'fire'),
    'frosts_chill': ('1d6', 'cold'),
}
FROSTS_CHILL_SLOW_FT = 10
STORMS_THUNDER_RANGE_FT = 60
STORMS_THUNDER_DIE = '1d8'
STONES_ENDURANCE_DIE = '1d12'
LARGE_SIZE_ID = 3

REACTION_TYPE_ON_HIT = 'giant_ancestry'

_DEFAULT_ANCESTRY_POOL = {'max': 'proficiency_bonus', 'restore_on': 'long_rest'}
_DEFAULT_LARGE_FORM_POOL = {'max': 1, 'restore_on': 'long_rest'}
_ONCE_PER_SHORT_REST = {'max': 1, 'restore_on': 'short_rest'}


def feature_label(feature):
    return FEATURE_LABELS.get(feature, str(feature).replace('_', ' ').title())


def _has_feature(entity, feature):
    try:
        return bool(entity.class_feature(feature))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Resource pools
# ---------------------------------------------------------------------------

def _pool_specs(entity):
    """Return ``(subrace_specs, base_specs)`` for ``entity``."""
    race_props = getattr(entity, 'race_properties', None)
    if isinstance(race_props, dict):
        base = race_props.get('resource_pools') or {}
        sub = {}
        subrace = entity.subrace() if callable(getattr(entity, 'subrace', None)) else None
        if subrace:
            sub = ((race_props.get('subrace') or {}).get(subrace) or {}).get('resource_pools') or {}
        return dict(sub), dict(base)
    props = getattr(entity, 'properties', None) or {}
    return {}, dict(props.get('resource_pools') or {})


def _default_pool(entity, feature):
    if feature == 'large_form':
        return 'large_form', dict(_DEFAULT_LARGE_FORM_POOL)
    if feature == 'stones_endurance':
        ruleset = getattr(getattr(entity, 'session', None), 'ruleset', None)
        model = ruleset.stones_endurance_uses_model() if ruleset is not None else 'once_per_short_rest'
        if model == 'once_per_short_rest':
            return 'stones_endurance', dict(_ONCE_PER_SHORT_REST)
    return 'giant_ancestry', dict(_DEFAULT_ANCESTRY_POOL)


def feature_pool(entity, feature):
    """Return ``(pool_name, spec)`` that ``feature`` draws its uses from."""
    sub, base = _pool_specs(entity)
    for specs in (sub, base):
        for name, spec in specs.items():
            if not isinstance(spec, dict):
                continue
            if feature in (spec.get('features') or []):
                return name, spec
    return _default_pool(entity, feature)


def _resolve_max(entity, spec):
    raw = spec.get('max', 1)
    if raw == 'proficiency_bonus':
        try:
            return max(1, int(entity.proficiency_bonus()))
        except Exception:
            return 2
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 1


def pool_name_for(entity, feature):
    return feature_pool(entity, feature)[0]


def uses_remaining(entity, feature):
    pool = entity.get_resource(pool_name_for(entity, feature))
    return pool.current if pool is not None else 0


def has_use(entity, feature):
    return _has_feature(entity, feature) and uses_remaining(entity, feature) > 0


def spend_use(entity, feature):
    return entity.consume_resource(pool_name_for(entity, feature))


def initialize_racial_traits(entity):
    """Register limited-use pools and attack-hit hooks for racial traits.

    Safe to call again (e.g. after a level up): existing pools keep their
    spent uses and gain any increase in maximum; hooks are not duplicated.
    """
    if not hasattr(entity, 'register_resource'):
        return
    pools = {}
    for feature in POOL_FEATURES:
        if not _has_feature(entity, feature):
            continue
        name, spec = feature_pool(entity, feature)
        pools.setdefault(name, spec)
    # Any other race ``resource_pools`` entry backing a feature the creature has
    # (Kender Fearless, ...).
    for specs in _pool_specs(entity):
        for name, spec in specs.items():
            if not isinstance(spec, dict) or name in pools:
                continue
            if any(_has_feature(entity, f) for f in (spec.get('features') or [])):
                pools[name] = spec
    for name, spec in pools.items():
        new_max = _resolve_max(entity, spec)
        restore_on = spec.get('restore_on', 'long_rest')
        existing = entity.get_resource(name)
        if existing is None:
            entity.register_resource(name, new_max, restore_on=restore_on)
        else:
            gained = max(0, new_max - existing.max_value)
            entity.register_resource(name, new_max, restore_on=restore_on,
                                     current=min(new_max, existing.current + gained))

    if any(_has_feature(entity, f) for f in ON_HIT_FEATURES):
        hooks = (getattr(entity, 'entity_event_hooks', None) or {}).get('on_attack_hit', [])
        if not any(isinstance(h.get('handler'), GiantAncestryStrikeEffect) for h in hooks):
            entity.register_event_hook('on_attack_hit', GiantAncestryStrikeEffect(entity), 'on_attack_hit')


# ---------------------------------------------------------------------------
# Ability checks (Powerful Build, Large Form)
# ---------------------------------------------------------------------------

def racial_check_advantage(entity, ability=None, purpose=None):
    """Advantage sources from racial traits for an ability check."""
    sources = []
    if purpose == 'escape_grapple' and _has_feature(entity, 'powerful_build'):
        sources.append('powerful_build')
    if ability in ('str', 'strength') and large_form_active(entity):
        sources.append('large_form')
    return sources


def large_form_active(entity):
    from natural20.actions.large_form_action import LargeFormEffect
    game_time = getattr(getattr(entity, 'session', None), 'game_time', 0)
    for descriptor in (getattr(entity, 'effects', None) or {}).get('size_override', []):
        if not isinstance(descriptor.get('effect'), LargeFormEffect):
            continue
        expiration = descriptor.get('expiration')
        if not expiration or expiration > game_time:
            return True
    return False


# ---------------------------------------------------------------------------
# Reaction selection helper
# ---------------------------------------------------------------------------

def _ask_controller(entity, battle, valid_actions, event):
    """Offer ``valid_actions`` to the entity's controller.

    Returns the chosen action or ``None``. With no controller the first
    option is used. Interactive (generator) controllers cannot pause damage
    resolution, so the reaction is used automatically, matching Hellish
    Rebuke and Wrath of the Storm.
    """
    controller = battle.controller_for(entity) if battle is not None else None
    if controller is None or not hasattr(controller, 'select_reaction'):
        return valid_actions[0]
    try:
        chosen = controller.select_reaction(
            entity, battle, battle.map_for(entity), valid_actions, event)
    except Exception:
        return valid_actions[0]
    if hasattr(chosen, 'send'):
        try:
            chosen.close()
        except Exception:
            pass
        return valid_actions[0]
    if isinstance(chosen, int):
        return valid_actions[chosen] if 0 <= chosen < len(valid_actions) else None
    if isinstance(chosen, list):
        chosen = chosen[0] if chosen else None
    return chosen if chosen in valid_actions else None


def _can_react(entity, battle):
    if battle is None or not entity.conscious():
        return False
    try:
        if entity.incapacitated():
            return False
    except Exception:
        pass
    if battle.entity_state_for(entity) is None:
        return False
    return entity.has_reaction(battle)


class GiantAncestryReactionAction(Action):
    """Reaction choice for Stone's Endurance / Storm's Thunder."""

    def __init__(self, session, source, feature, target=None):
        super().__init__(session, source, feature)
        self.feature = feature
        self.target = target

    def label(self):
        return f"{feature_label(self.feature)} ({uses_remaining(self.source, self.feature)} left)"

    def button_label(self):
        return self.label()

    def __str__(self):
        return self.label()

    __repr__ = __str__

    def build_map(self):
        return self

    def resolve(self, session, map, opts=None):
        return self


# ---------------------------------------------------------------------------
# Stone's Endurance (damage reduction before HP loss)
# ---------------------------------------------------------------------------

def stones_endurance_reduction(battle, entity, damage, damage_type=None, attacker=None, item=None):
    """Offer Stone's Endurance; return how much of ``damage`` it prevents."""
    if damage <= 0 or not has_use(entity, 'stones_endurance') or not _can_react(entity, battle):
        return 0
    action = GiantAncestryReactionAction(entity.session, entity, 'stones_endurance', target=attacker)
    chosen = _ask_controller(entity, battle, [action], {
        'type': 'stones_endurance',
        'trigger': 'on_damage_taken',
        'attacker': attacker,
        'target': entity,
        'damage': damage,
        'damage_type': damage_type,
    })
    if not chosen:
        return 0
    roll = DieRoll.roll(f"{STONES_ENDURANCE_DIE}+{entity.con_mod()}", battle=battle, entity=entity,
                        description='dice_roll.features.stones_endurance')
    reduced = max(0, min(int(damage), roll.result()))
    battle.consume(entity, 'reaction')
    spend_use(entity, 'stones_endurance')
    entity.session.event_manager.received_event({
        'event': 'stones_endurance',
        'source': entity,
        'roll': roll,
        'reduced': reduced,
        'damage': damage,
    })
    return reduced


# ---------------------------------------------------------------------------
# Storm's Thunder (retaliation after taking damage)
# ---------------------------------------------------------------------------

def storms_thunder_reaction(battle, entity, attacker, damage_opts=None):
    """Offer Storm's Thunder against ``attacker``; returns damage events."""
    if battle is None or attacker is None or attacker is entity:
        return []
    if not has_use(entity, 'storms_thunder') or not _can_react(entity, battle):
        return []
    if attacker.dead() or (hasattr(attacker, 'object') and attacker.object()):
        return []
    bmap = battle.map_for(entity)
    try:
        if bmap is None or bmap.distance(entity, attacker) * bmap.feet_per_grid > STORMS_THUNDER_RANGE_FT:
            return []
    except Exception:
        return []

    action = GiantAncestryReactionAction(entity.session, entity, 'storms_thunder', target=attacker)
    chosen = _ask_controller(entity, battle, [action], {
        'type': 'storms_thunder',
        'trigger': 'on_damage_taken',
        'attacker': attacker,
        'target': entity,
    })
    if not chosen:
        return []

    battle.consume(entity, 'reaction')
    spend_use(entity, 'storms_thunder')
    damage_roll = DieRoll.roll(STORMS_THUNDER_DIE, battle=battle, entity=entity,
                               description='dice_roll.features.storms_thunder')
    event = {
        'source': entity,
        'target': attacker,
        'attack_name': feature_label('storms_thunder'),
        'damage_type': 'thunder',
        'damage_roll': damage_roll,
        'damage': damage_roll.result(),
        'type': 'spell_damage',
        'source_feature': 'storms_thunder',
    }
    entity.session.event_manager.received_event({
        'event': 'storms_thunder',
        'source': entity,
        'target': attacker,
        'damage': damage_roll.result(),
        'roll': damage_roll,
    })
    attacker.take_damage(damage_roll.result(), battle=battle, damage_type='thunder',
                         session=entity.session, item=event)
    return [event]


# ---------------------------------------------------------------------------
# On-hit riders (Fire's Burn, Frost's Chill, Hill's Tumble)
# ---------------------------------------------------------------------------

def _damage_value(damage):
    if damage is None:
        return 0
    try:
        return int(damage.result()) if hasattr(damage, 'result') else int(damage)
    except (TypeError, ValueError):
        return 0


def on_hit_options(entity, hit_result):
    """Features usable on this hit (empty when no rider applies)."""
    if not hit_result or not hit_result.get('hit?'):
        return []
    target = hit_result.get('target')
    if target is None or hit_result.get('grapple_instead'):
        return []
    if hasattr(target, 'object') and target.object():
        return []
    if _damage_value(hit_result.get('damage')) <= 0:
        return []
    options = []
    for feature in ON_HIT_FEATURES:
        if not has_use(entity, feature):
            continue
        if feature == 'hills_tumble':
            try:
                if target.size_identifier() > LARGE_SIZE_ID or target.prone():
                    continue
            except Exception:
                continue
        options.append(feature)
    return options


def _stored_choice(attack_action, entity):
    """``(asked, choice)`` for a previous Giant Ancestry prompt on this attack."""
    if attack_action is None:
        return False, None
    for source, result in (getattr(attack_action, 'async_reactions', None) or {}).get(REACTION_TYPE_ON_HIT, []):
        if source == entity:
            return True, result
    return False, None


class GiantAncestryStrikeEffect:
    """``on_attack_hit`` hook offering the creature's on-hit ancestry boon."""

    def __init__(self, owner):
        self.owner = owner

    def __str__(self):
        return 'giant_ancestry'

    def on_attack_hit(self, entity, opts=None):
        opts = opts or {}
        if entity != self.owner:
            return []
        hit_result = opts.get('result') or {}
        battle = hit_result.get('battle')
        target = hit_result.get('target')
        features = on_hit_options(entity, hit_result)
        if not features:
            return []

        valid_actions = [
            GiantAncestryStrikeAction(entity.session, entity, feature, target, hit_result)
            for feature in features
        ]
        attack_action = opts.get('action')
        asked, selected = _stored_choice(attack_action, entity)
        if not asked:
            controller = battle.controller_for(entity) if battle is not None else None
            if controller is None or not hasattr(controller, 'select_reaction'):
                selected = valid_actions[0]
            else:
                try:
                    selected = controller.select_reaction(
                        entity, battle, battle.map_for(entity), valid_actions, {
                            'type': REACTION_TYPE_ON_HIT,
                            'trigger': 'on_attack_hit',
                            'source': entity,
                            'target': target,
                            'result': hit_result,
                            'features': features,
                        })
                except Exception:
                    selected = valid_actions[0]
                if hasattr(selected, 'send'):
                    raise AsyncReactionHandler(entity, selected, attack_action, REACTION_TYPE_ON_HIT)

        if isinstance(selected, int):
            selected = valid_actions[selected] if 0 <= selected < len(valid_actions) else None
        if isinstance(selected, list):
            selected = selected[0] if selected else None
        if not isinstance(selected, GiantAncestryStrikeAction):
            return []
        resolved = selected.resolve(entity.session, battle.map_for(entity) if battle else None,
                                    {'battle': battle})
        return list(resolved.result or [])


class GiantAncestryStrikeAction(Action):
    """Apply one on-hit ancestry boon. Spends a use when committed."""

    def __init__(self, session, source, feature, target=None, attack_result=None):
        super().__init__(session, source, feature)
        self.feature = feature
        self.target = target
        self.attack_result = attack_result or {}
        self._resolved = False

    def label(self):
        return f"{feature_label(self.feature)} ({uses_remaining(self.source, self.feature)} left)"

    def button_label(self):
        return self.label()

    def name(self):
        return self.label()

    def __str__(self):
        return self.label()

    __repr__ = __str__

    def build_map(self):
        return self

    def compute_hit_probability(self, battle, opts=None):
        return 1.0

    def avg_damage(self, battle, opts=None):
        dice = ON_HIT_DAMAGE.get(self.feature)
        if not dice:
            return 0
        count, sides = dice[0].split('d')
        return int(count) * (int(sides) + 1) / 2

    def resolve(self, session, map, opts=None):
        # Re-resolving the attack after another async reaction must not
        # roll the rider twice.
        if self._resolved:
            return self
        battle = (opts or {}).get('battle')
        items = [{
            'type': 'giant_ancestry_use',
            'source': self.source,
            'target': self.target,
            'feature': self.feature,
            'battle': battle,
        }]
        dice = ON_HIT_DAMAGE.get(self.feature)
        if dice:
            expression, damage_type = dice
            critical = bool(self.attack_result.get('critical'))
            damage_roll = DieRoll.roll(expression, crit=critical, battle=battle, entity=self.source,
                                       description=f"dice_roll.features.{self.feature}")
            items.append({
                'type': 'giant_ancestry_damage',
                'source': self.source,
                'target': self.target,
                'attack_name': feature_label(self.feature),
                'damage_type': damage_type,
                'damage_roll': damage_roll,
                'damage': damage_roll,
                'critical': False,
                'feature': self.feature,
            })
        if self.feature == 'frosts_chill':
            items.append({'type': 'giant_ancestry_slow', 'source': self.source,
                          'target': self.target, 'distance': FROSTS_CHILL_SLOW_FT})
        if self.feature == 'hills_tumble':
            items.append({'type': 'giant_ancestry_prone', 'source': self.source, 'target': self.target})
        self.result = items
        self._resolved = True
        return self

    @staticmethod
    def apply(battle, item, session=None):
        item_type = item.get('type')
        if item_type not in ('giant_ancestry_use', 'giant_ancestry_damage',
                             'giant_ancestry_slow', 'giant_ancestry_prone'):
            return None
        source = item['source']
        target = item.get('target')
        if session is None:
            session = battle.session if battle else source.session

        if item_type == 'giant_ancestry_use':
            spend_use(source, item['feature'])
            session.event_manager.received_event({
                'event': 'giant_ancestry',
                'source': source,
                'target': target,
                'feature': item['feature'],
                'label': feature_label(item['feature']),
            })
        elif item_type == 'giant_ancestry_damage':
            from natural20.utils.attack_util import damage_event
            if target.passive():
                target.is_passive = False
            damage_event(item, battle)
        elif item_type == 'giant_ancestry_slow':
            from natural20.weapon_mastery import _entity_uid
            current = int(getattr(target, '_mastery_slow_ft', 0) or 0)
            target._mastery_slow_ft = max(current, int(item.get('distance', FROSTS_CHILL_SLOW_FT)))
            target._mastery_slow_from = _entity_uid(source)
        elif item_type == 'giant_ancestry_prone':
            target.do_prone()
        return item
