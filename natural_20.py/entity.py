class Entity():
    def __init__(self, name, description, attributes = {}):
        self.name = name
        self.description = description
        self.attributes = attributes
    
    def __str__(self):
        return f"{self.name}: {self.description}"
    
    def __repr__(self):
        return f"{self.name}: {self.description}"
    
    def name(self):
        return self.name
    
    def hp(self):
        return self.attributes["hp"]
