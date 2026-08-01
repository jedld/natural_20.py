from natural20.utils.target_validation import (
    add_validation_issue,
    clear_validation,
    extend_validation_issues,
    has_validation_failures,
)
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


class BardicInspirationPrompt(Exception):
    """Pause resolution so the player can choose whether to spend BI."""

    def __init__(self, entity, die_roll, context, generator):
        self.entity = entity
        self.die_roll = die_roll
        self.context = context
        self.generator = generator

    def resolve(self):
        return self.generator

    def send(self, use_die):
        try:
            self.generator.send(bool(use_die))
        except StopIteration as e:
            return e.value
        return None

class Action:
    def __init__(self, session, source, action_type, opts=None):
        self.uid = uuid.uuid4()
        self.source = source
        self.session = session
        self.action_type = action_type
        self.as_bonus_action = False
        self.async_reactions = {}
        self.errors = []
        self.validation_issues = []
        self.result = []
        self.committed = False
        self.disabled = False
        self.disabled_reason = None
        self.legendary_action = False

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
    
    def object_action_prompt(self):
        return None

    def to_dict(self):
        return {
            "action_type": self.action_type,
            "source": self.source.entity_uid
        }

    def label(self):
        p = inflect.engine()
        if not self.action_type:
            return "actions"
        return p.plural(self.action_type)

    def validate(self, battle_map, target=None, battle=None):
        clear_validation(self)

    def clear_validation_errors(self):
        clear_validation(self)

    def add_validation_issue(self, entry, /, **params):
        add_validation_issue(self, entry, **params)

    def extend_validation_issues(self, issues):
        extend_validation_issues(self, issues)

    def validation_failed(self) -> bool:
        return has_validation_failures(self)

    def button_label(self):
        return None

    def button_image(self):
        return None

    @staticmethod
    def apply(battle, item, session=None) -> list:
        return []

    def resolve(self, session, map, opts=None):
        pass
    
    def t(self, k, **kwargs):
        return i18n.t(k, **kwargs)

    def to_h(self):
        return {
            "action_type": self.action_type,
            "source": self.source.entity_uid
        }
