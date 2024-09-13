import pdb

class Multiattack:

  def multi_attack_actions(self, session, battle):
    pass

  def clear_multiattack(self, battle):
    entity_state = battle.entity_state_for(self)
    entity_state["multiattack"] = {}

  def multiattack(self, battle, npc_action):
    if not npc_action:
      return False
    if not self.class_feature("multiattack"):
      return False

    entity_state = battle.entity_state_for(self)

    if not entity_state["multiattack"]:
      return False
    if not npc_action.get("multiattack_group"):
      return False

    for group, attacks in entity_state["multiattack"].items():
      if npc_action["name"] in attacks:
        return True

    return False
