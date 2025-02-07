import inflect
import i18n
import uuid
# typed: true
class AsyncReactionHandler(Exception):
    def __init__(self, source, generator, action, reaction_type):
        self.reaction_type = reaction_type
        self.generator = generator
        self.source = source
        self.action = action

    def resolve(self):
        for gen in self.generator:
            print(f"{gen}")
            try:
                yield gen
            except StopIteration as e:
                return e.value

    def send(self, result):
        self.action.add_reaction(self.reaction_type, self.source, result)

    def __repr__(self):
        return f"{self.source} -> {self.reaction_type} on {self.action} by {self.action.source}"
    
    def __str__(self):
        return f"{self.source} -> {self.reaction_type} on {self.action} by {self.action.source}"

class Action:
    def __init__(self, session, source, action_type, opts=None):
        self.uid = uuid.uuid4()
        self.source = source
        self.session = session
        self.action_type = action_type
        self.as_bonus_action = False
        self.async_reactions = {}
        self.errors = []
        self.result = []
        self.committed = False
        self.disabled = False
        self.disabled_reason = None

        if opts is None:
            opts = {}
        self.opts = opts

    def add_reaction(self, reaction_type, source, result):
        if reaction_type not in self.async_reactions:
            self.async_reactions[reaction_type] = []
        self.async_reactions[reaction_type] = (source, result)

    def has_async_reaction_for_source(self, source, reaction_type):
        for key, value in self.async_reactions.items():
            if key == reaction_type and value[0] == source:
                return value[1]
        return False

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
