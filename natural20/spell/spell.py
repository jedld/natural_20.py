import re

def camel_case_to_human_readable(camel_case_string):
    # Insert spaces before uppercase letters and capitalize the first letter
    human_readable = re.sub(r'(?<!^)(?=[A-Z])', '_', camel_case_string).capitalize()
    return human_readable.lower()

def consume_resource(battle, source, item):
    amt, resource = item["casting_time"].split(":")
    spell_level = item["level"]

    if resource == "action":
        battle.consume(source, "action")
    elif resource == "reaction":
        battle.consume(source, "reaction")

    source.consume_spell_slot(spell_level) if spell_level > 0 else None

class AttackHook:
    def after_attack_roll(battle, entity, attacker, attack_roll, effective_ac, opts=None):
        pass

class Spell:
    def __init__(self, session, source, spell_name, details):
        self.session = session
        self.name = spell_name
        self.properties = details
        self.action = None
        self.source = source
        self.target = None
        self.errors = []

    def short_name(self):
        # remove the spell suffix and turn Camelcase to space separated
        return camel_case_to_human_readable(self.name[:-5])

    def label(self):
        return self.t(f"spell.{self.name}")

    def clone(self):
        spell = self.__class__(self.session, self.source, self.name, self.properties)
        spell.target = self.target
        spell.action = self.action
        return spell

    @property
    def id(self):
        return self.properties.get('id')

    def consume(self, battle):
        consume_resource(battle, self.source, self.properties)

    @staticmethod
    def apply(battle, item):
        pass

    def validate(self, action):
        self.errors.clear()

    def load_spell_info(self):
        return self.session.load_spell(self.name)

    def t(self, token, spell=None, options=None):
        if options is None:
            options = {}
        return token
    
    def compute_hit_probability(self, battle, opts = None):
        return 1.0
