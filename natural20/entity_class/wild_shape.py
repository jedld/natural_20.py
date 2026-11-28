"""Wild Shape (Druid) — transform / revert helpers.

Implements the 5e Wild Shape mechanic for the Druid class. The legal beast
pool scales with druid level and campaign ruleset (see
``Ruleset.wild_shape_max_cr`` / ``wild_shape_flight_level`` /
``wild_shape_swim_level``):

* 2014: CR <= 1/4 (no fly, no swim) at level 2; swim at 4; CR <= 1 and fly
  at 8. Circle of the Moon: CR 1 at 2 and swim ignored from 2 (+1 CR every
  4 levels to CR 5).
* 2024: CR <= 1/4 at 2-3, CR <= 1/2 at 4-7, CR <= 1 at 8+; swim always
  allowed; fly at 8. Circle of the Moon: CR 1 at 3 ... CR 6 at 18.

The duration is tracked but the engine does not auto-tick mid-combat hours;
transformations end on revert, on 0 HP, or via the explicit revert action.

The implementation snapshots druid-side combat-relevant state, then
overlays the beast statblock loaded from ``templates/npcs/<beast>.yml``.
On revert the snapshot is restored. If beast HP is reduced to 0, the
overflow damage is applied to the druid form.
"""

import copy
import yaml
from natural20.yaml_loader import load_campaign_resource_path


# Beasts available at druid level 2 (CR <= 1/4, no fly / swim speed) when no
# session catalog is available; kept as a fallback for bare-unit contexts.
WILD_SHAPE_BEASTS_LEVEL_2 = ('wolf', 'giant_rat', 'boar', 'cat')


def _load_beast_yaml(session, beast_id):
  """Load a beast NPC YAML from campaign/import/template resources."""
  try:
    return load_campaign_resource_path(session.root_path, f'npcs/{beast_id}.yml')
  except FileNotFoundError as exc:
    raise FileNotFoundError(
      f'beast statblock not found for {beast_id} in campaign/import/template resources'
    ) from exc


def druid_circle(druid):
  """Circle/subclass name stored on the character sheet, if any."""
  props = getattr(druid, 'properties', None) or {}
  for key in ('druidic_circle', 'druid_circle', 'druid_subclass', 'subclass'):
    value = props.get(key)
    if value:
      return str(value)
  return None


def _ruleset_for(ruleset=None, session=None):
  if ruleset is not None:
    return ruleset
  ruleset = getattr(session, 'ruleset', None)
  if ruleset is not None:
    return ruleset
  from natural20.ruleset.factory import get_ruleset
  return get_ruleset('5e-2014')


def _cr_value(beast_props):
  cr = (beast_props or {}).get('cr')
  try:
    return float(cr) if cr is not None else 999.0
  except (TypeError, ValueError):
    return 999.0


def can_assume(beast_props, druid_level, ruleset=None, session=None, circle=None):
  """Return True if the beast statblock is legal for this druid."""
  if druid_level is None or druid_level < 2:
    return False
  ruleset = _ruleset_for(ruleset, session)
  max_cr = ruleset.wild_shape_max_cr(druid_level, circle)
  if _cr_value(beast_props) > max_cr:
    return False
  if beast_props.get('speed_fly') and druid_level < ruleset.wild_shape_flight_level(circle):
    return False
  if beast_props.get('speed_swim') and druid_level < ruleset.wild_shape_swim_level(circle):
    return False
  return True


def available_beasts(druid_level, session=None, ruleset=None, circle=None):
  """Return the beast ids the druid may assume, scanned from the NPC catalog.

  Every YAML under the campaign/import/expansion/template ``npcs`` roots with
  ``race: [beast, ...]`` is a candidate; legality follows the campaign
  ruleset (CR cap plus fly/swim level gates). Without a session, falls back
  to the level-2 CR <= 1/4 ground-and-water-free list.
  """
  if druid_level is None or druid_level < 2:
    return ()
  ruleset = _ruleset_for(ruleset, session)
  if session is None:
    return tuple(WILD_SHAPE_BEASTS_LEVEL_2)

  found = []
  seen = set()
  roots_fn = getattr(session, '_category_roots', None)
  if not callable(roots_fn):
    return tuple(WILD_SHAPE_BEASTS_LEVEL_2)
  for folder in roots_fn('npcs', include_templates=True):
    for path in sorted(folder.glob('*.yml')):
      key = path.stem.lower()
      if key in seen:
        continue
      seen.add(key)
      try:
        with path.open('r', encoding='utf-8') as fh:
          props = yaml.safe_load(fh)
      except (OSError, yaml.YAMLError):
        continue
      if not isinstance(props, dict) or 'key' in props and props['key'] is None:
        continue
      race = props.get('race') or []
      if isinstance(race, str):
        race = [race]
      if 'beast' not in [str(entry).strip().lower() for entry in race]:
        continue
      if can_assume(props, druid_level, ruleset=ruleset, circle=circle):
        found.append(key)
  return tuple(sorted(found))


def available_forms(druid):
  """Available beast ids for a specific druid entity (session + ruleset +
  circle aware)."""
  session = getattr(druid, 'session', None)
  return available_beasts(getattr(druid, 'druid_level', None),
                          session=session,
                          ruleset=getattr(session, 'ruleset', None),
                          circle=druid_circle(druid))


def _wild_shape_duration_rounds(druid_level):
  """Half druid level (rounded down) hours, in 6-second rounds."""
  hours = max(1, druid_level // 2)
  return hours * 600


def _apply_beast_overlay(druid, props, set_full_hp=True, beast_id=None, replace_mental=False):
  """Overlay beast statblock onto druid (no snapshot capture).

  Wild Shape keeps the druid's mental scores; Polymorph replaces all six
  (``replace_mental``).
  """
  new_scores = copy.deepcopy(druid.ability_scores)
  beast_ability = props.get('ability', {})
  keys = ('str', 'dex', 'con', 'int', 'wis', 'cha') if replace_mental else ('str', 'dex', 'con')
  for k in keys:
    if beast_ability.get(k) is not None:
      new_scores[k] = beast_ability[k]
  druid.ability_scores = new_scores

  beast_max_hp = int(props.get('max_hp') or 1)
  druid.properties['max_hp'] = beast_max_hp
  if set_full_hp:
    druid.attributes['hp'] = beast_max_hp
  if 'max_hp' in druid.attributes:
    druid.attributes['max_hp'] = beast_max_hp

  druid.properties['speed'] = props.get('speed', druid.properties.get('speed'))
  druid.properties['size'] = props.get('size', druid.properties.get('size'))
  druid.properties['race'] = props.get('race', ['beast'])
  druid.properties['default_ac'] = props.get('default_ac',
                                              druid.properties.get('default_ac'))
  druid.properties['attributes'] = props.get('attributes', []) or []
  druid.properties['resistances'] = props.get('resistances', []) or []

  # Token / portrait overlay so the VTT renders the beast form.
  beast_token = props.get('token')
  if beast_token is not None:
    druid.properties['token'] = copy.deepcopy(beast_token)
  beast_token_image = props.get('token_image')
  if not beast_token_image:
    kind = props.get('kind') or beast_id
    if kind:
      beast_token_image = f"token_{str(kind).lower().replace(' ', '_')}.png"
  if beast_token_image:
    druid.properties['token_image'] = beast_token_image

  druid.npc_actions = copy.deepcopy(props.get('actions', []))


def transform(druid, beast_id):
  """Snapshot druid state and overlay the beast statblock onto it."""
  props = _load_beast_yaml(druid.session, beast_id)
  ruleset = getattr(getattr(druid, 'session', None), 'ruleset', None)
  if not can_assume(props, getattr(druid, 'druid_level', None),
                    ruleset=ruleset, circle=druid_circle(druid)):
    raise ValueError(f'beast {beast_id} not legal at druid level '
                     f'{getattr(druid, "druid_level", None)}')
  assume_form(druid, beast_id, props,
              duration_rounds=_wild_shape_duration_rounds(getattr(druid, 'druid_level', 2) or 2))


def assume_form(druid, beast_id, props, *, source='wild_shape', replace_mental=False,
                duration_rounds=None, meta=None):
  """Snapshot the creature and overlay ``props`` (a beast statblock).

  ``source`` tags who owns the form (``wild_shape`` or ``polymorph``);
  ``meta`` is extra JSON-safe data kept on the state (e.g. caster uid).
  """
  snapshot = {
    'ability_scores': copy.deepcopy(druid.ability_scores),
    'max_hp_property': druid.properties.get('max_hp'),
    'hp_current': druid.attributes.get('hp'),
    'speed': druid.properties.get('speed'),
    'size': druid.properties.get('size'),
    'race': copy.deepcopy(druid.properties.get('race')),
    'default_ac': druid.properties.get('default_ac'),
    'attributes_list': copy.deepcopy(druid.properties.get('attributes')),
    'resistances': copy.deepcopy(druid.properties.get('resistances')),
    'token': copy.deepcopy(druid.properties.get('token')),
    'token_image_property': druid.properties.get('token_image'),
    'has_token_key': 'token' in druid.properties,
    'has_token_image_key': 'token_image' in druid.properties,
  }

  _apply_beast_overlay(druid, props, set_full_hp=True, beast_id=beast_id,
                       replace_mental=replace_mental)

  druid._wild_shape_state = {
    'form': beast_id,
    'beast_props': props,
    'snapshot': snapshot,
    'duration_rounds_left': duration_rounds,
    'source': source,
    'replace_mental': bool(replace_mental),
    **(meta or {}),
  }


def scrub_properties_for_serialization(properties, state):
  """Return a deepcopy of properties with the wild-shape overlay rolled
  back using the saved snapshot. Used by ``to_dict`` so persisted
  properties match the un-transformed humanoid form."""
  if not state:
    return copy.deepcopy(properties)
  snap = state.get('snapshot') or {}
  out = copy.deepcopy(properties)
  if 'max_hp_property' in snap and snap['max_hp_property'] is not None:
    out['max_hp'] = snap['max_hp_property']
  for key, snap_key in (
    ('speed', 'speed'),
    ('size', 'size'),
    ('race', 'race'),
    ('default_ac', 'default_ac'),
    ('attributes', 'attributes_list'),
    ('resistances', 'resistances'),
  ):
    val = snap.get(snap_key)
    if val is None:
      out.pop(key, None)
    else:
      out[key] = copy.deepcopy(val)
  # Token / token_image: only restore the key if the original had it.
  for key, snap_key, has_key in (
    ('token', 'token', 'has_token_key'),
    ('token_image', 'token_image_property', 'has_token_image_key'),
  ):
    if snap.get(has_key):
      out[key] = copy.deepcopy(snap.get(snap_key))
    else:
      out.pop(key, None)
  return out


def reapply_after_load(druid):
  """After ``from_dict`` rebuilds the PC, re-apply the beast overlay if
  ``_wild_shape_state`` is present. ``attributes['hp']`` is set by the
  caller from the persisted ``data['hp']``."""
  state = getattr(druid, '_wild_shape_state', None)
  if not state:
    return
  beast = state.get('beast_props')
  if not beast:
    return
  _apply_beast_overlay(druid, beast, set_full_hp=False, beast_id=state.get('form'),
                       replace_mental=state.get('replace_mental', False))


def revert(druid, overflow_damage=0, battle=None):
  """Revert the druid to humanoid form, restoring snapshotted state.

  ``overflow_damage`` is applied to the druid's saved current HP if the
  beast form was dropped to 0. Mental stats were never changed.
  """
  state = getattr(druid, '_wild_shape_state', None)
  if not state:
    return
  snap = state['snapshot']

  druid.ability_scores = snap['ability_scores']

  pre_revert_max = snap['max_hp_property']
  if pre_revert_max is not None:
    druid.properties['max_hp'] = pre_revert_max
  if 'max_hp' in druid.attributes and pre_revert_max is not None:
    druid.attributes['max_hp'] = pre_revert_max

  saved_hp = snap['hp_current']
  if saved_hp is None:
    saved_hp = pre_revert_max or 0
  new_hp = max(0, saved_hp - max(0, int(overflow_damage)))
  druid.attributes['hp'] = new_hp

  for key, snap_key in (
    ('speed', 'speed'),
    ('size', 'size'),
    ('race', 'race'),
    ('default_ac', 'default_ac'),
    ('attributes', 'attributes_list'),
    ('resistances', 'resistances'),
  ):
    val = snap[snap_key]
    if val is None:
      druid.properties.pop(key, None)
    else:
      druid.properties[key] = val

  # Restore token / portrait. Only re-add the key if the original had it.
  for key, snap_key, has_key in (
    ('token', 'token', 'has_token_key'),
    ('token_image', 'token_image_property', 'has_token_image_key'),
  ):
    if snap.get(has_key):
      druid.properties[key] = copy.deepcopy(snap.get(snap_key))
    else:
      druid.properties.pop(key, None)

  druid.npc_actions = []
  druid._wild_shape_state = None

  # Falling to 0 in beast form leaves the druid at 0 if overflow exceeds
  # the saved HP — humanoid form drops unconscious.
  if new_hp <= 0 and battle is not None:
    try:
      druid.make_unconscious()
    except Exception:
      pass


def is_wild_shaped(druid):
  """True while any beast form overlay is active (Wild Shape or Polymorph)."""
  return bool(getattr(druid, '_wild_shape_state', None))


def form_source(druid):
  state = getattr(druid, '_wild_shape_state', None)
  return (state.get('source') or 'wild_shape') if state else None


def current_form(druid):
  state = getattr(druid, '_wild_shape_state', None)
  return state['form'] if state else None
