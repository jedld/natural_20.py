import pdb


from collections import Counter
from itertools import combinations_with_replacement


def expand_multiattack_entries(raw):
  """Normalize the NPC ``multiattack`` YAML into lists of action names.

  Entries are comma-separated name lists (``"claws,claws2"``; a name may
  repeat, ``"blade,blade,axe"``) or ``{any_of: [blade, axe], count: 3}``,
  which expands to every combination of ``count`` attacks drawn from
  ``any_of`` ("three attacks in any combination").
  """
  if isinstance(raw, (str, dict)):
    raw = [raw]
  combos = []
  for entry in raw or []:
    if isinstance(entry, dict):
      options = [str(n).strip() for n in (entry.get('any_of') or []) if str(n).strip()]
      count = int(entry.get('count', 2) or 0)
      if options and count > 0:
        combos.extend(list(c) for c in combinations_with_replacement(options, count))
      continue
    names = [n.strip() for n in str(entry).split(',') if n.strip()]
    if names:
      combos.append(names)
  return combos


def multiattack_combos(entity):
  """Allowed attack combinations from the NPC ``multiattack`` YAML list.

  Combos are only enforced when every name refers to a ``multiattack_group``
  action and there is more than one combo or a name repeats; otherwise
  group membership alone applies.
  """
  raw = (getattr(entity, 'properties', None) or {}).get('multiattack') or []
  group_names = {
    a.get('name') for a in (entity.properties.get('actions') or [])
    if a.get('multiattack_group')
  }
  combos = expand_multiattack_entries(raw)
  if any(n not in group_names for combo in combos for n in combo):
    return []
  repeats = any(len(set(combo)) < len(combo) for combo in combos)
  return combos if (len(combos) > 1 or repeats) else []


def narrow_multiattack_groups(entity_state, used_name=None):
  """Consume ``used_name`` from the combos and restrict groups to what is still possible.

  Group lists hold one entry per attack still available, so a name allowed
  twice by some combo appears twice.
  """
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
  allowed = Counter()
  for combo in combos:
    for name, n in Counter(combo).items():
      allowed[name] = max(allowed[name], n)
  for group, attacks in (entity_state.get('multiattack') or {}).items():
    names = list(dict.fromkeys(attacks))
    attacks[:] = [name for name in names for _ in range(allowed.get(name, 0))]


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
