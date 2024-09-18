import inflect
import i18n
# typed: true
class Action:
    def __init__(self, session, source, action_type, opts=None):
        self.source = source
        self.session = session
        self.action_type = action_type
        self.as_bonus_action = False
        self.errors = []
        self.result = []

        if opts is None:
            opts = {}
        self.opts = opts

    def clone(self):
        return Action(self.session, self.source, self.action_type, self.opts)

    @staticmethod
    def can(entity, battle, options=None):
        return False

    @staticmethod
    def to_type(klass_name):
        return klass_name.lower().replace("action", "").strip()

    def name(self):
        return str(self.action_type)

    def __repr__(self):
        return str(self.action_type).capitalize()
    
    def __str__(self):
        return str(self.action_type).capitalize()

    def to_dict(self):
        return {
            "action_type": self.action_type,
            "source": self.source.entity_uid
        }

    def label(self):
        p = inflect.engine()
        return p.plural(self.action_type)

    def validate(self, target=None):
        pass

    @staticmethod
    def apply(battle, item, session=None):
        pass

    def resolve(self, session, map, opts=None):
        pass
    
    def t(self, k, **kwargs):
        return i18n.t(k, **kwargs)

    def to_h(self):
        return {
            "action_type": self.action_type,
            "source": self.source.entity_uid
        }
