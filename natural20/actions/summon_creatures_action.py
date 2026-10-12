"""Actions for YAML ``summons`` abilities (see ``natural20/utils/summons.py``)."""

from natural20.action import Action
from natural20.utils import summons as summon_utils


def _has_resource(entity, battle, cost):
    if battle is None or entity not in getattr(battle, 'entities', {}):
        return True
    if cost == 'bonus_action':
        return entity.total_bonus_actions(battle) > 0
    return entity.total_actions(battle) > 0


class SummonCreaturesAction(Action):
    """Call creatures from a ``summons`` entry; ``summon`` + ``option`` pick
    which entry and which creature option."""

    def __init__(self, session, source, action_type='summon_creatures', opts=None):
        super().__init__(session, source, action_type, opts)
        opts = opts or {}
        self.summon_name = opts.get('summon')
        self.option_index = opts.get('option')
        self.as_bonus_action = summon_utils.summon_cost(self._config()) == 'bonus_action'

    def _config(self):
        if not self.summon_name:
            configs = summon_utils.summon_configs(self.source)
            return configs[0] if configs else None
        return summon_utils.summon_config(self.source, self.summon_name)

    def _option(self):
        config = self._config()
        options = (config or {}).get('options') or []
        if self.option_index is None or not (0 <= int(self.option_index) < len(options)):
            return None
        return options[int(self.option_index)]

    def label(self):
        option = self._option()
        if option is None:
            return summon_utils.summon_title(self._config())
        return summon_utils.option_label(self.source, self._config(), option)

    def describe(self):
        """One-line summary for AI prompts."""
        config = self._config() or {}
        parts = [self.label()]
        if config.get('arrival'):
            parts.append(f"arrive in {config['arrival']} rounds")
        remaining = summon_utils.uses_remaining(self.source, config)
        if remaining is not None:
            parts.append(f"{remaining} use(s) left today")
        return ' - '.join(parts)

    def button_label(self):
        return self.label()

    def button_image(self):
        return 'summon'

    def to_h(self):
        data = super().to_h()
        if self.summon_name and self.option_index is not None:
            data['choice'] = f"{self.summon_name}:{self.option_index}"
        return data

    def ai_value(self, battle, enemy_count=1):
        option = self._option()
        if option is None:
            return 0.0
        return summon_utils.option_ai_value(self.source, self._config(), option, enemy_count)

    def __repr__(self):
        return f"SummonCreatures({self.summon_name}:{self.option_index})"

    @staticmethod
    def can(entity, battle, options=None):
        options = options or {}
        for config, index, _option in summon_utils.available_summon_options(entity, battle):
            if options.get('summon') and options['summon'] != config['name']:
                continue
            if options.get('option') is not None and int(options['option']) != index:
                continue
            if _has_resource(entity, battle, summon_utils.summon_cost(config)):
                return True
        return False

    @classmethod
    def options_for(cls, session, entity, battle):
        """One fully-specified action per usable summon option."""
        actions = []
        for config, index, _option in summon_utils.available_summon_options(entity, battle):
            if _has_resource(entity, battle, summon_utils.summon_cost(config)):
                actions.append(cls(session, entity, 'summon_creatures', {'summon': config['name'], 'option': index}))
        return actions

    def build_map(self):
        if self.summon_name and self.option_index is not None:
            return self
        choices = [
            [summon_utils.option_label(self.source, config, option), f"{config['name']}:{index}"]
            for config, index, option in summon_utils.available_summon_options(self.source, None)
        ]

        def set_choice(choice):
            name, _, index = str(choice).rpartition(':')
            self.summon_name = name
            self.option_index = int(index)
            self.as_bonus_action = summon_utils.summon_cost(self._config()) == 'bonus_action'
            return self

        if len(choices) == 1:
            return set_choice(choices[0][1])
        return {
            'action': self,
            'param': [{'type': 'select_choice', 'choices': choices}],
            'next': set_choice,
        }

    def resolve(self, session, map_, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        config = self._config()
        issue = summon_utils.summon_issue(self.source, config, battle, self._option())
        if self._option() is None:
            issue = issue or 'no creature option chosen'
        if issue:
            self.errors.append(issue)
            self.result = []
            return self
        self.result = [{
            'type': 'summon_creatures',
            'source': self.source,
            'summon': config['name'],
            'option': int(self.option_index),
            'cost': summon_utils.summon_cost(config),
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'summon_creatures':
            return
        source = item['source']
        if battle is not None and source in getattr(battle, 'entities', {}):
            battle.consume(source, item.get('cost', 'action'))
        summon_utils.begin_summon(source, item['summon'], item['option'], battle)


class DismissSummonsAction(Action):
    """Send all creatures from one ``summons`` entry away."""

    def __init__(self, session, source, action_type='dismiss_summons', opts=None):
        super().__init__(session, source, action_type, opts)
        opts = opts or {}
        self.summon_name = opts.get('summon')
        if not self.summon_name:
            configs = summon_utils.dismissable_configs(source)
            self.summon_name = configs[0]['name'] if configs else None
        config = summon_utils.summon_config(source, self.summon_name)
        self.as_bonus_action = summon_utils.dismiss_cost(config) == 'bonus_action'

    def label(self):
        config = summon_utils.summon_config(self.source, self.summon_name)
        count = len(summon_utils.active_summons(self.source, self.summon_name))
        return f"Dismiss {summon_utils.summon_title(config)} ({count})"

    describe = label

    def button_label(self):
        return 'Dismiss Summons'

    def button_image(self):
        return 'summon'

    def __repr__(self):
        return f"DismissSummons({self.summon_name})"

    @staticmethod
    def can(entity, battle, options=None):
        for config in summon_utils.dismissable_configs(entity):
            if _has_resource(entity, battle, summon_utils.dismiss_cost(config)):
                return True
        return False

    def build_map(self):
        return self

    def resolve(self, session, map_, opts=None):
        opts = opts or {}
        config = summon_utils.summon_config(self.source, self.summon_name)
        self.result = [{
            'type': 'dismiss_summons',
            'source': self.source,
            'summon': self.summon_name,
            'cost': summon_utils.dismiss_cost(config) or 'bonus_action',
            'battle': opts.get('battle'),
        }] if config else []
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'dismiss_summons':
            return
        source = item['source']
        if battle is not None and source in getattr(battle, 'entities', {}):
            battle.consume(source, item.get('cost', 'bonus_action'))
        summon_utils.dismiss_summons(source, battle, name=item.get('summon'))
