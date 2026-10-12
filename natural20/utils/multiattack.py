import pdb


def multiattack_combos(entity):
  """Allowed attack combinations from the NPC ``multiattack`` YAML list.

  Each entry is a comma-separated list of action names that may be used
  together in one Multiattack (``"claws,claws2"``, ``"claws,bite"``). Combos
  are only enforced when there is more than one and every name refers to a
  ``multiattack_group`` action; otherwise group membership alone applies.
  """
  raw = (getattr(entity, 'properties', None) or {}).get('multiattack') or []
  if isinstance(raw, str):
    raw = [raw]
  group_names = {
    a.get('name') for a in (entity.properties.get('actions') or [])
    if a.get('multiattack_group')
  }
  combos = []
  for entry in raw:
    names = [n.strip() for n in str(entry).split(',') if n.strip()]
    if not names or any(n not in group_names for n in names):
      return []
    combos.append(names)
  return combos if len(combos) > 1 else []


def narrow_multiattack_groups(entity_state, used_name=None):
  """Consume ``used_name`` from the combos and restrict groups to what is still possible."""
  combos = entity_state.get('multiattack_combos') or []
  if not combos:
    return
  if used_name is not None:
    remaining = []
    for combo in combos:
      if used_name in combo:
        combo = list(combo)
        combo.remove(used_name)
        remaining.append(combo)
    combos = remaining
    entity_state['multiattack_combos'] = combos
  allowed = set()
  for combo in combos:
    allowed.update(combo)
  for group, attacks in (entity_state.get('multiattack') or {}).items():
    attacks[:] = [a for a in attacks if a in allowed]


class Multiattack:

  def multi_attack_actions(self, session, battle):
    pass

  def clear_multiattack(self, battle):
    entity_state = battle.entity_state_for(self)
    entity_state["multiattack"] = {}
    entity_state["multiattack_hits"] = {}
    entity_state["multiattack_combos"] = []
    entity_state["multiattack_started"] = False

  def multiattack(self, battle, npc_action):
    if not npc_action or not self.has_multiattack():
      return False

    multiattack_state = battle.entity_state_for(self).get("multiattack")
    if not multiattack_state or not npc_action.get("multiattack_group"):
      return False

    for attacks in multiattack_state.values():
      if npc_action["name"] in attacks:
        if npc_action.get("multiattack_dependent_on") in attacks:
          return False
        return True

    return False
