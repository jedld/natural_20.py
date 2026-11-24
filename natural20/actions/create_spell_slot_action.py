from natural20.action import Action


class CreateSpellSlotAction(Action):
    """Font of Magic — Flexible Casting (Sorcerer, SRD p.66).

    Both conversion directions, as a bonus action:

    * Sorcery points -> spell slot: 2/3/5/6/7 points for a level 1-5 slot.
      The SRD table also gates the *maximum slot level you may create* by
      sorcerer level (2nd/3rd/5th/7th/9th), so a level-2 sorcerer is only
      ever offered level-1 slots (Nov-23 report item 5). The created slot
      disappears on a long rest (the slot table is rebuilt there).
    * Spell slot -> sorcery points (same 2/3/5/6/7 values), never gaining
      more points than the Font of Magic pool maximum.

    Issue #6 item 61: the points resource existed but nothing could spend
    it, so the conversion never surfaced in any action menu.
    """

    # SRD 5.2.1 Flexible Casting conversion values (both directions).
    SLOT_COSTS = {1: 2, 2: 3, 3: 5, 4: 6, 5: 7}
    # Minimum sorcerer level that may CREATE a slot of each level.
    MIN_CREATOR_LEVELS = {1: 2, 2: 3, 3: 5, 4: 7, 5: 9}

    # ------------------------------------------------------------------ #

    @staticmethod
    def _creator_level(entity):
        level = int(getattr(entity, 'sorcerer_level', 0) or 0)
        if not level:
            classes = (getattr(entity, 'properties', None) or {}).get('classes') or {}
            level = int(classes.get('sorcerer', 0) or 0)
        return level

    @classmethod
    def creatable_levels(cls, entity, points=None):
        """Slot levels this creature may create from points right now."""
        if points is None:
            points = int(getattr(entity, 'sorcery_points', 0) or 0)
        level = cls._creator_level(entity)
        return {
            slot_level for slot_level, cost in cls.SLOT_COSTS.items()
            if cost <= points and level >= cls.MIN_CREATOR_LEVELS[slot_level]
        }

    @classmethod
    def convertible_slots(cls, entity):
        """Slot levels this creature could convert into points right now
        (has the slot, and the gain stays within the points maximum)."""
        if not callable(getattr(entity, 'spell_slots_count', None)):
            return set()
        points = int(getattr(entity, 'sorcery_points', 0) or 0)
        max_points = int(getattr(entity, 'max_sorcery_points', lambda: 0)() or 0)
        out = set()
        for slot_level, gain in cls.SLOT_COSTS.items():
            try:
                have = entity.spell_slots_count(slot_level, 'sorcerer')
            except Exception:
                have = 0
            if have and have > 0 and points + gain <= max_points:
                out.add(slot_level)
        return out

    @classmethod
    def can(cls, entity, battle):
        if not entity.class_feature('font_of_magic'):
            return False
        if not cls.creatable_levels(entity) and not cls.convertible_slots(entity):
            return False
        if battle is None:
            return True
        state = battle.entity_state_for(entity)
        if not state or state.get('bonus_action', 0) <= 0:
            return False
        return True

    def label(self):
        return 'Flexible Casting'

    def __str__(self):
        return "uses Flexible Casting to convert Sorcery Points and spell slots"

    __repr__ = __str__

    # ------------------------------------------------------------------ #

    def clone(self):
        action = CreateSpellSlotAction(self.session, self.source,
                                       self.action_type, self.opts)
        action.slot_level = int(getattr(self, 'slot_level', 0) or 0)
        action.to_points = bool(getattr(self, 'to_points', False))
        return action

    def to_dict(self):
        hash = super().to_dict()
        hash['slot_level'] = int(getattr(self, 'slot_level', 0) or 0)
        hash['to_points'] = bool(getattr(self, 'to_points', False))
        return hash

    @staticmethod
    def from_dict(hash):
        action = CreateSpellSlotAction(hash.get('session'), hash.get('source'),
                                       hash['action_type'])
        action.slot_level = int(hash.get('slot_level', 0) or 0)
        action.to_points = bool(hash.get('to_points', False))
        return action

    def build_map(self):
        source = self.source
        choices = [
            [f"Level {level} spell slot ({cost} Sorcery Points)", level]
            for level, cost in sorted(self.SLOT_COSTS.items())
            if level in self.creatable_levels(source)
        ]
        choices += [
            [f"Sorcery Points for level {level} spell slot ({cost} Points)",
             f"to_points:{level}"]
            for level, cost in sorted(self.SLOT_COSTS.items())
            if level in self.convertible_slots(source)
        ]
        if not choices:
            return None

        def set_level(level):
            if isinstance(level, (list, tuple)):
                level = level[1]
            action = self.clone()
            if isinstance(level, str) and level.startswith('to_points:'):
                action.to_points = True
                action.slot_level = int(level.split(':', 1)[1])
            else:
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
            raise ValueError(f"cannot convert a level {level} slot with sorcery points")
        if getattr(self, 'to_points', False):
            # Refuse to create points beyond what the pool allows, and
            # require the slot to exist.
            if (level not in self.convertible_slots(self.source)):
                raise ValueError(
                    f"cannot convert a level {level} slot to Sorcery Points")
            item_type = 'convert_slot_to_points'
        else:
            if level not in self.creatable_levels(self.source):
                raise ValueError(
                    f"cannot create a level {level} slot from sorcery points")
            item_type = 'create_spell_slot'
        self.result = [{
            'source': self.source,
            'type': item_type,
            'level': level,
            'cost': cost,
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] not in ('create_spell_slot', 'convert_slot_to_points'):
            return
        source = item['source']
        level = int(item['level'])
        cost = int(item['cost'])
        to_points = item['type'] == 'convert_slot_to_points'
        state = battle.entity_state_for(source) if battle else None

        if to_points:
            if (not callable(getattr(source, 'consume_spell_slot', None))
                    or not callable(getattr(source, 'recover_sorcery_points', None))):
                return
            if (callable(getattr(source, 'spell_slots_count', None))
                    and not source.spell_slots_count(level, 'sorcerer')):
                if battle:
                    session.event_manager.received_event({
                        'source': source, 'event': 'flavor',
                        'text': 'no level %d spell slot left' % level})
                return
            source.consume_spell_slot(level, 'sorcerer')
            gained = source.recover_sorcery_points(cost)
            if state is not None:
                state['bonus_action'] -= 1
            if battle:
                session.event_manager.received_event({
                    'source': source,
                    'event': 'convert_slot_to_points',
                    'level': level,
                    'points_gained': gained,
                    'points_left': int(getattr(source, 'sorcery_points', 0) or 0),
                })
            return

        # points -> slot
        if not source.consume_sorcery_points(cost):
            if battle:
                session.event_manager.received_event({
                    'source': source, 'event': 'flavor',
                    'text': 'not enough Sorcery Points'})
            return
        if state is not None:
            state['bonus_action'] -= 1
        slots = source.spell_slots.setdefault('sorcerer', {})
        slots[level] = int(slots.get(level, 0) or 0) + 1
        if battle:
            session.event_manager.received_event({
                'source': source,
                'event': 'create_spell_slot',
                'level': level,
                'cost': cost,
                'points_left': int(getattr(source, 'sorcery_points', 0) or 0),
            })

    @staticmethod
    def describe(event):
        if event.get('event') == 'convert_slot_to_points':
            return (f"{event['source'].name.colorize('green')} converts a level "
                    f"{event['level']} spell slot into "
                    f"{event.get('points_gained', 0)} Sorcery Points")
        return (f"{event['source'].name.colorize('green')} converts "
                f"{event['cost']} Sorcery Points into a level {event['level']} "
                f"spell slot")
