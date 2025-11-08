from natural20.action import Action


class LayOnHandsAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.heal_amt = 0
        self.target = None
        self.mode = None
        self.cure_targets = []
        self.cure_labels = []
        self.max_heal = 0

    @staticmethod
    def can(entity, battle):
        if not hasattr(entity, 'lay_on_hands_max_pool'):
            return False
        if getattr(entity, 'lay_on_hands_count', 0) <= 0:
            return False
        return battle is None or entity.total_actions(battle) > 0

    def label(self):
        return 'Lay on Hands'

    def __str__(self):
        return "LayOnHands"

    def __repr__(self):
        return "LayOnHands"

    def build_map(self):
        def set_target(target):
            self.target = target
            self.mode = None
            self.heal_amt = 0
            self.cure_targets = []
            self.cure_labels = []
            self.errors = []

            if target is None:
                self.errors.append('Target required')
                return self

            if self._is_undead_or_construct(target):
                self.errors.append('Lay on Hands has no effect on undead or constructs')
                return self

            self.max_heal = self._max_heal_for(target)
            usage_step = self._build_usage_step()
            return usage_step

        return {
            "action": self,
            "param": [
                {
                    "type": "select_target",
                    "range": 5,
                    "target_types": ["self", "allies"],
                    "num": 1
                }
            ],
            "next": set_target
        }

    def _build_usage_step(self):
        choices = []
        if self.max_heal > 0:
            for amount in range(1, self.max_heal + 1):
                choices.append([f"Heal {amount} HP", f"heal:{amount}"])

        cure_choices = self._cure_choices()
        choices.extend(cure_choices)

        if not choices:
            self.errors.append('Target cannot benefit from Lay on Hands')
            return self

        def set_usage(choice):
            value = self._extract_choice_value(choice)
            if value is None:
                self.errors.append('Invalid Lay on Hands selection')
                return self

            if value.startswith('heal:'):
                try:
                    amount = int(value.split(':', 1)[1])
                except ValueError:
                    amount = 0
                self.mode = 'heal'
                self.heal_amt = amount
                self.cure_targets = []
                self.cure_labels = []
            elif value.startswith('cure:'):
                parts = value.split(':')
                if len(parts) < 2:
                    self.errors.append('Invalid Lay on Hands selection')
                    return self
                cure_type = parts[1]
                self.mode = 'cure'
                self.heal_amt = 0
                if cure_type == 'poison':
                    self.cure_targets = ['poisoned']
                    self.cure_labels = ['poison']
                elif cure_type == 'disease' and len(parts) > 2:
                    disease_id = parts[2]
                    self.cure_targets = [disease_id]
                    self.cure_labels = [self._condition_label(disease_id)]
                else:
                    self.errors.append('Invalid Lay on Hands selection')
            else:
                self.errors.append('Invalid Lay on Hands selection')
            return self

        return {
            "param": [
                {
                    "type": "select_choice",
                    "choices": choices,
                    "num": 1
                }
            ],
            "next": set_usage
        }

    def _cure_choices(self):
        choices = []
        pool = getattr(self.source, 'lay_on_hands_count', 0)
        if pool < 5 or self.target is None:
            return choices

        if self._target_poisoned(self.target):
            choices.append(['Neutralize poison (5 HP)', 'cure:poison'])

        for disease in self._disease_statuses(self.target):
            label = self._condition_label(disease)
            choices.append([f'Cure {label} (5 HP)', f'cure:disease:{disease}'])

        return choices

    @staticmethod
    def build(session, source):
        action = LayOnHandsAction(session, source, 'lay_on_hands')
        return action.build_map()

    def resolve(self, _session, battle_map, opts=None):
        if opts is None:
            opts = {}

        if self.errors:
            return self

        target = self.target
        if target is None:
            self.errors = ['Target required']
            return self

        if not self.validate(battle_map, target):
            return self

        battle = opts.get('battle') if opts else None

        if self.mode == 'heal':
            heal_amt = min(self.heal_amt, self._max_heal_for(target))
            self.heal_amt = heal_amt
            self.result = [{
                'source': self.source,
                'target': target,
                'hp': heal_amt,
                'hp_spent': heal_amt,
                'mode': 'heal',
                'type': 'lay_on_hands',
                'battle': battle
            }]
        else:
            cost = 5 * len(self.cure_targets)
            self.result = [{
                'source': self.source,
                'target': target,
                'hp': 0,
                'hp_spent': cost,
                'mode': 'cure',
                'conditions': list(self.cure_targets),
                'condition_labels': list(self.cure_labels),
                'type': 'lay_on_hands',
                'battle': battle
            }]

        return self

    def validate(self, battle_map, target=None):
        if self.errors is None:
            self.errors = []
        else:
            self.errors.clear()
        def add_error(message):
            if message not in self.errors:
                self.errors.append(message)

        target_entity = target or self.target
        if target_entity is None:
            add_error('Target required')
            return False

        if self._is_undead_or_construct(target_entity):
            add_error('Lay on Hands has no effect on undead or constructs')

        if battle_map:
            distance = battle_map.distance(self.source, target_entity) * battle_map.feet_per_grid
            if distance > 5:
                add_error('Target is out of reach')

        pool_remaining = getattr(self.source, 'lay_on_hands_count', 0)
        if pool_remaining <= 0:
            add_error('No Lay on Hands pool remaining')

        if self.mode == 'heal':
            missing_hp = max(0, target_entity.max_hp() - target_entity.hp())
            if missing_hp <= 0:
                add_error('Target already at full health')
            if self.heal_amt <= 0:
                add_error('Select a positive amount of healing')
            if self.heal_amt > min(pool_remaining, missing_hp):
                add_error('Heal amount exceeds the remaining pool or missing hit points')
        elif self.mode == 'cure':
            if not self.cure_targets:
                add_error('Select a disease or poison to cure')
            required_pool = 5 * len(self.cure_targets)
            if pool_remaining < required_pool:
                add_error('Not enough Lay on Hands pool remaining')
            for condition in self.cure_targets:
                if condition == 'poisoned':
                    if not self._target_poisoned(target_entity):
                        add_error('Target is not poisoned')
                else:
                    if condition not in getattr(target_entity, 'statuses', []):
                        add_error(f'Target is not afflicted with {self._condition_label(condition)}')
        else:
            add_error('Select how to use Lay on Hands')

        return len(self.errors) == 0

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'lay_on_hands':
            return

        source = item.get('source')
        target = item.get('target')
        if source is None or target is None:
            return

        mode = item.get('mode')
        if mode == 'heal':
            amount = max(0, item.get('hp', 0))
            actual = source.lay_on_hands(target, amount)
            item['hp'] = actual
            item['hp_spent'] = actual
        elif mode == 'cure':
            conditions = item.get('conditions', [])
            cured = source.lay_on_hands_cure(target, conditions)
            item['cured'] = cured
        else:
            return

        if battle:
            battle.consume(source, 'action')

    @staticmethod
    def describe(event):
        mode = event.get('mode', 'heal')
        source_label = event['source'].name.colorize('green') if event.get('source') else 'Someone'
        target = event.get('target')
        target_label = target.name.colorize('green') if target else 'their ally'

        if mode == 'cure':
            cured = event.get('conditions') or event.get('cured') or []
            labels = event.get('condition_labels') or [LayOnHandsAction._condition_label(c) for c in cured]
            summary = ', '.join(labels) if labels else 'no afflictions'
            cost = event.get('hp_spent', 5 * len(cured or []))
            return f"{source_label} channels Lay on Hands to cure {summary} on {target_label} (spends {cost} HP)"

        amount = event.get('hp', 0)
        return f"{source_label} lays on hands, restoring {amount} HP to {target_label}"

    def _max_heal_for(self, target):
        pool = getattr(self.source, 'lay_on_hands_count', 0)
        missing_hp = max(0, target.max_hp() - target.hp())
        return max(0, min(pool, missing_hp))

    @staticmethod
    def _extract_choice_value(choice):
        if isinstance(choice, (list, tuple)):
            if len(choice) == 0:
                return None
            if len(choice) == 1:
                return LayOnHandsAction._extract_choice_value(choice[0])
            if len(choice) >= 2:
                return choice[1]
        if isinstance(choice, str):
            return choice
        return None

    @staticmethod
    def _is_undead_or_construct(target):
        race_tags = []
        if hasattr(target, 'properties'):
            race_tags = target.properties.get('race', []) or []
        if isinstance(race_tags, str):
            race_tags = [race_tags]
        normalized = {str(tag).lower() for tag in race_tags}
        if hasattr(target, 'undead') and callable(target.undead):
            if target.undead():
                normalized.add('undead')
        return 'undead' in normalized or 'construct' in normalized

    @staticmethod
    def _target_poisoned(target):
        if hasattr(target, 'poisoned') and target.poisoned():
            return True
        statuses = getattr(target, 'statuses', [])
        return any(isinstance(status, str) and status == 'poisoned' for status in statuses)

    @staticmethod
    def _disease_statuses(target):
        statuses = getattr(target, 'statuses', [])
        diseases = []
        for status in statuses:
            if isinstance(status, str) and 'disease' in status.lower():
                diseases.append(status)
        return diseases

    @staticmethod
    def _condition_label(condition):
        if not condition:
            return 'condition'
        label = condition.replace('_', ' ').replace('-', ' ')
        return label.strip().title() if label else 'condition'
