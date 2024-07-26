class Spell:
    def __init__(self, session, source, spell_name, details):
        self.session = session
        self.name = spell_name
        self.properties = details
        self.source = source
        self.errors = []

    def label(self):
        return self.t(f"spell.{self.name}")

    @property
    def id(self):
        return self.properties.get('id')

    @staticmethod
    def apply(battle, item):
        pass

    def validate(self, action):
        self.errors.clear()

    def t(self, token, spell=None, options=None):
        if options is None:
            options = {}
        return token
