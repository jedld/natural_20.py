class Action():
    def __init__(self, name, description, effect):
        self.name = name
        self.description = description
        self.effect = effect

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def __call__(self):
        return self.effect()