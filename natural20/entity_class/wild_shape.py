"""Wild Shape (Druid) — transform / revert helpers.

Implements the 5e SRD 2014 Wild Shape mechanic for the Druid class. At
level 2 the druid may transform into a beast of CR <= 1/4 with no
flying or swimming speed. The duration is tracked but the engine does
not auto-tick mid-combat hours; transformations end on revert, on
0 HP, or via the explicit revert action.

The implementation snapshots druid-side combat-relevant state, then
overlays the beast statblock loaded from ``templates/npcs/<beast>.yml``.
On revert the snapshot is restored. If beast HP is reduced to 0, the
overflow damage is applied to the druid form.
"""

import copy
import os
import yaml


# Beasts available at druid level 2 (CR <= 1/4, no fly / swim speed).
WILD_SHAPE_BEASTS_LEVEL_2 = ('wolf', 'giant_rat', 'boar', 'cat')


def _load_beast_yaml(session, beast_id):
  """Load a beast NPC yaml from session.root_path/npcs/<beast_id>.yml."""
  path = os.path.join(session.root_path, 'npcs', f'{beast_id}.yml')
  if not os.path.exists(path):
    raise FileNotFoundError(f'beast statblock not found: {path}')
  with open(path) as f:
    return yaml.safe_load(f)


def available_beasts(druid_level):
  """Return the list of beast ids the druid may assume at this level."""
  if druid_level is None or druid_level < 2:
    return ()
  # L2 only: CR <= 1/4, no fly / no swim. (Higher levels TBD.)
  return tuple(WILD_SHAPE_BEASTS_LEVEL_2)


def can_assume(beast_props, druid_level):
  """Return True if the beast statblock is legal at this druid level."""
  if druid_level is None or druid_level < 2:
    return False
  cr = beast_props.get('cr')
  try:
    cr_val = float(cr) if cr is not None else 999.0
  except (TypeError, ValueError):
    cr_val = 999.0
  if cr_val > 0.25:
    return False
  # No fly speed at L2.
  if beast_props.get('speed_fly'):
    return False
  # No swim speed at L2.
  if beast_props.get('speed_swim'):
    return False
  return True


def _wild_shape_duration_rounds(druid_level):
  """Half druid level (rounded down) hours, in 6-second rounds."""
  hours = max(1, druid_level // 2)
  return hours * 600


def _apply_beast_overlay(druid, props, set_full_hp=True, beast_id=None):
  """Overlay beast statblock onto druid (no snapshot capture)."""
  new_scores = copy.deepcopy(druid.ability_scores)
  beast_ability = props.get('ability', {})
  for k in ('str', 'dex', 'con'):
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
  if not can_assume(props, getattr(druid, 'druid_level', None)):
    raise ValueError(f'beast {beast_id} not legal at druid level '
                     f'{getattr(druid, "druid_level", None)}')

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

  _apply_beast_overlay(druid, props, set_full_hp=True, beast_id=beast_id)

  druid._wild_shape_state = {
    'form': beast_id,
    'beast_props': props,
    'snapshot': snapshot,
    'duration_rounds_left': _wild_shape_duration_rounds(
      getattr(druid, 'druid_level', 2) or 2),
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
  _apply_beast_overlay(druid, beast, set_full_hp=False, beast_id=state.get('form'))


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
  return bool(getattr(druid, '_wild_shape_state', None))


def current_form(druid):
  state = getattr(druid, '_wild_shape_state', None)
  return state['form'] if state else None
