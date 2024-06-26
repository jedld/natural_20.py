import inflect
# typed: true
class Action:
    def __init__(self, session, source, action_type, opts={}):
        self.source = source
        self.session = session
        self.action_type = action_type
        self.errors = []
        self.result = []
        self.opts = opts

    @staticmethod
    def can(entity, battle, options={}):
        return False

    @staticmethod
    def to_type(klass_name):
        return klass_name.lower().replace("action", "").strip()

    def name(self):
        return str(self.action_type)

    def to_str(self):
        return str(self.action_type).capitalize()

    def to_dict(self):
        return {
            "action_type": self.action_type,
            "source": self.source.entity_uid
        }

    def label(self):
        p = inflect.engine()
        return p.plural(self.action_type)

    def validate(self):
        pass

    @staticmethod
    def apply(battle, item):
        pass

    def resolve(self, session, map, opts={}):
        pass
    
    def t(self, k, options={}):
        return k
