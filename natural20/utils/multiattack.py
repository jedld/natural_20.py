import pdb

class Multiattack:

  def multi_attack_actions(self, session, battle):
    pass

  def clear_multiattack(self, battle):
    entity_state = battle.entity_state_for(self)
    entity_state["multiattack"] = {}

  def multiattack(self, battle, npc_action):
    if not npc_action or not self.class_feature("multiattack"):
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
