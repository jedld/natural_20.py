from natural20.entity import Entity
import yaml

class PlayerCharacter(Entity):
  def __init__(self, template, name=None):
    super(PlayerCharacter, self).__init__(name, f"PC {name}")
    with open(template, 'r') as file:
      self.properties = yaml.safe_load(file)
    race_file = self.properties['race']
    with open(f"templates/races/{race_file}.yml") as file:
      self.race_properties = yaml.safe_load(file)
    self.ability_scores = self.properties.get('ability', {})

  def size(self):
      return self.properties.get("size") or self.race_properties.get('size')
  
  def token(self):
      return self.properties['token']
