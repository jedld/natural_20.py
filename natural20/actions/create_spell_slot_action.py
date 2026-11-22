from natural20.action import Action


class CreateSpellSlotAction(Action):
    """Font of Magic — Flexible Casting (Sorcerer, SRD p.66).

    As a bonus action you can convert sorcery points into spell slots:
    2/3/5/6/7 points for a level 1-5 slot. The slot disappears when you
    finish a long rest (the sorcerer's slot table is rebuilt from scratch
    there, so newly created extra slots are dropped automatically).
    Issue #6 item 61: the points resource existed but nothing could spend
    it, so the conversion never surfaced in any action menu.
    """

    # SRD 5.2.1 Font of Magic conversion costs.
    SLOT_COSTS = {1: 2, 2: 3, 3: 5, 4: 6, 5: 7}

    @staticmethod
    def can(entity, battle):
        if not entity.class_feature('font_of_magic'):
            return False
        points = int(getattr(entity, 'sorcery_points', 0) or 0)
        if points < min(CreateSpellSlotAction.SLOT_COSTS.values()):
            return False
        if battle is None:
            return True
        state = battle.entity_state_for(entity)
        if not state or state.get('bonus_action', 0) <= 0:
            return False
        # Never propose a slot the caster is too low-level to ever have?
        # RAW allows any level 1-5 regardless; keep the raw rule.
        return True

    def label(self):
        return 'Convert Sorcery Points'

    def __str__(self):
        return "converts sorcery points into a spell slot"

    __repr__ = __str__

    def clone(self):
        action = CreateSpellSlotAction(self.session, self.source,
                                       self.action_type, self.opts)
        action.slot_level = int(getattr(self, 'slot_level', 0) or 0)
        return action

    def to_dict(self):
        hash = super().to_dict()
        hash['slot_level'] = int(getattr(self, 'slot_level', 0) or 0)
        return hash

    @staticmethod
    def from_dict(hash):
        action = CreateSpellSlotAction(hash.get('session'), hash.get('source'),
                                       hash['action_type'])
        action.slot_level = int(hash.get('slot_level', 0) or 0)
        return action

    def build_map(self):
        points = int(getattr(self.source, 'sorcery_points', 0) or 0)
        choices = [
            [f"Level {level} spell slot ({cost} Sorcery Points)", level]
            for level, cost in sorted(self.SLOT_COSTS.items())
            if cost <= points
        ]
        if not choices:
            return None

        def set_level(level):
            if isinstance(level, (list, tuple)):
                level = level[1]
            action = self.clone()
            action.slot_level = int(level)
            return action

        return {'param': [{'type': 'select_choice', 'num': 1,
                           'choices': choices}],
                'next': set_level}

    @classmethod
    def build(cls, session, source):
        action = CreateSpellSlotAction(session, source, 'create_spell_slot')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        battle = opts.get("battle") if opts else None
        level = int(getattr(self, 'slot_level', 0) or 0)
        cost = self.SLOT_COSTS.get(level)
        if cost is None:
            raise ValueError(f"cannot create a level {level} slot from sorcery points")
        self.result = [{
            'source': self.source,
            'type': 'create_spell_slot',
            'level': level,
            'cost': cost,
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'create_spell_slot':
            return
        source = item['source']
        level = int(item['level'])
        cost = int(item['cost'])
        if battle is None:
            session = session or source.session
            # Out-of-battle bookkeeping: spend points and add the slot.
            if not source.consume_sorcery_points(cost):
                return
            slots = source.spell_slots.setdefault('sorcerer', {})
            slots[level] = int(slots.get(level, 0) or 0) + 1
            return
        state = battle.entity_state_for(source)
        if not source.consume_sorcery_points(cost):
            session.event_manager.received_event({
                'source': source, 'event': 'flavor',
                'text': 'not enough Sorcery Points'})
            return
        if state is not None:
            state['bonus_action'] -= 1
        slots = source.spell_slots.setdefault('sorcerer', {})
        slots[level] = int(slots.get(level, 0) or 0) + 1
        session.event_manager.received_event({
            'source': source,
            'event': 'create_spell_slot',
            'level': level,
            'cost': cost,
            'points_left': int(getattr(source, 'sorcery_points', 0) or 0),
        })

    @staticmethod
    def describe(event):
        return (f"{event['source'].name.colorize('green')} converts "
                f"{event['cost']} Sorcery Points into a level {event['level']} "
                f"spell slot")
