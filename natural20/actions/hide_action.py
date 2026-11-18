from natural20.action import Action

class HideAction(Action):
    as_bonus_action: bool

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.as_bonus_action = False

    @staticmethod
    def can(entity, battle, options=None):
        if options is None:
            options = {}

        if battle is None:
            return True

        return bool(battle.maps) and entity.total_actions(battle) > 0

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        action = HideAction(session, source, 'hide')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        stealth_roll = self.source.stealth_check(opts.get('battle', None))

        battle = opts.get('battle')

        def map_of(entity):
            # session.map_for_entity filters by the active map set and can
            # miss both maps, which used to skip every visibility check.
            found = battle.map_for(entity) if battle else None
            return found or self.session.map_for_entity(entity)

        source_map = map_of(self.source) or map
        if battle:
            opponents = [opp for opp in battle.opponents_of(self.source) if opp.conscious()]
        else:
            opponents = []

        hide_failed_reasons = []
        if source_map:
            heavily_obscured = source_map.is_heavily_obscured(self.source)
        else:
            heavily_obscured = False

        ruleset = getattr(self.source.session, 'ruleset', None)
        is_2024 = bool(ruleset and getattr(ruleset, 'name', '') == '5e-2024')

        was_hidden = 'hidden' in self.source.statuses

        if is_2024:
            # 2024: you can hide only when out of every foe's line of
            # sight and heavily obscured or behind three-quarters/total
            # cover, then pass a DC 15 Dexterity (Stealth) check.
            if battle is not None and source_map is not None:
                _can, cover_reasons = source_map.can_hide(self.source, None, battle)
                if not _can:
                    hide_failed_reasons.extend(cover_reasons)
            if int(stealth_roll.result()) < 15:
                hide_failed_reasons.append('stealth check failed (DC 15)')
        elif was_hidden:
            # Already hidden and unspotted: re-hiding is judged on the NEW
            # roll, not covered by the old hidden status — any foe with line
            # of sight to you contests it with their passive Perception, and
            # a roll that would leave you observable fails the attempt.
            for opp in opponents:
                opponent_map = map_of(opp)
                if source_map != opponent_map:
                    continue
                if not source_map:
                    continue
                # can_see with the hidden status ON answers "does this foe
                # currently perceive me here?": it contests their Perception
                # against the old hidden roll.
                if source_map.can_see(opp, self.source):
                    hide_failed_reasons.append(f"{opp.label()} can see {self.source.label()}")
                    continue
                # They do not see me now, but would they see me if I stepped
                # out and hid again? Judge the NEW roll against their passive
                # Perception only for foes watching this spot.
                self.source.statuses.remove('hidden')
                try:
                    watches_spot = source_map.can_see(opp, self.source)
                finally:
                    self.source.statuses.append('hidden')
                if not watches_spot:
                    continue
                opp_pp = opp.passive_perception()
                if heavily_obscured:
                    opp_pp -= 5
                if opp.class_feature('keen_sight_and_smell'):
                    opp_pp += 5
                if stealth_roll < opp_pp:
                    hide_failed_reasons.append(
                        f"{opp.label()} would notice {self.source.label()}")
        else:
            # 2014, not yet hidden: you can't hide from a creature that can
            # see you clearly. There is no stealth-versus-perception contest
            # at this point: foes who can't see you search later (can_see
            # compares passive Perception against the hidden roll).
            for opp in opponents:
                opponent_map = map_of(opp)
                if source_map != opponent_map:
                    continue
                if source_map and source_map.can_see(opp, self.source):
                    hide_failed_reasons.append(f"{opp.label()} can see {self.source.label()}")

        if hide_failed_reasons:
            self.result = [{
                'source': self.source,
                'type': 'hide',
                'bonus_action': self.as_bonus_action,
                'result': 'failed',
                'roll': stealth_roll,
                'battle': battle,
                'reason': hide_failed_reasons
            }]
        else:
            self.result = [{
                'source': self.source,
                'bonus_action': self.as_bonus_action,
                'type': 'hide',
                'result': 'success',
                'roll': stealth_roll,
                'battle': battle
            }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'hide':
            event_manager = battle.event_manager if battle else session.event_manager if session else None

            if item['result'] == 'success':
                if event_manager:
                    event_manager.received_event({
                        'source': item['source'],
                        'roll': item['roll'],
                        'result' : 'success',
                        'event': 'hide'
                    })
                item['source'].do_hide(item['roll'].result())
            else:
                if event_manager:
                    event_manager.received_event({
                        'source': item['source'],
                        'roll': item['roll'],
                        'result' : 'failed',
                        'event': 'hide',
                        'reason': item['reason']
                    })

            if battle:
                if item.get('bonus_action'):
                    battle.consume(item['source'], 'bonus_action')
                else:
                    battle.consume(item['source'], 'action')

class HideBonusAction(HideAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    @staticmethod
    def can(entity, battle):
        if not battle or entity.total_bonus_actions(battle) <= 0:
            return False

        if entity.any_class_feature(['cunning_action', 'nimble_escape']):
            return True

        if entity.any_class_feature(["shadow_stealth"]):
            map_entity = battle.map_for(entity)
            pos_x, pos_y = map_entity.position_of(entity)
            return map_entity.light_at(pos_x, pos_y) <= 0.5

        return False
