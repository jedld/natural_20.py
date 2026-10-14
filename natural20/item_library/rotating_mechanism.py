"""A heavy fixture that can be turned to face a compass direction
(a rotating statue, a capstan, a turntable).

Object YAML (see ``docs/CAMPAIGN_BUILDING.md`` -> "Rotating mechanisms")::

    type: rotating_statue
    facing: east
    facings: [north, east, south, west]
    rotate:
      requires_check: investigation  # hidden until someone passes this ability_checks entry
      ability: strength              # check rolled by the creature turning it
      dc: 22
      combined_score: 40             # helpers in reach whose summed Strength reaches this
                                     # turn it without a roll
      cost: action                   # in combat
    events:
      - event: face_north            # fired after a successful turn
        update_state: {target: [secret_door_n], state: 'unsecret,unlocked,opened'}

Events ``face_<direction>`` and ``rotate`` fire after a successful turn. The
state ``facing:<direction>`` (from ``update_state``) turns it silently, e.g.
to swing back after springing a trap.
"""

from natural20.item_library.object import Object


class RotatingMechanism(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.facings = list(self.properties.get('facings') or ['north', 'east', 'south', 'west'])
        self.facing = self.properties.get('facing', self.facings[0])
        self.rotate_config = dict(self.properties.get('rotate') or {})
        self.mechanism_known = bool(self.properties.get('mechanism_known', False))

    def label(self):
        base = super().label()
        return f"{base} (facing {self.facing})"

    def interactable(self, entity=None):
        return not self.is_concealed

    def _required_check(self):
        return self.rotate_config.get('requires_check')

    def can_rotate(self):
        return self.mechanism_known or not self._required_check()

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = super().available_interactions(entity, battle, admin=admin)
        if self.is_concealed and not admin:
            return interactions
        if not (self.can_rotate() or admin):
            return interactions
        no_action = (battle is not None and self.rotate_config.get('cost', 'action') == 'action'
                     and entity is not None and entity.total_actions(battle) == 0)
        prompt = self.rotate_config.get('prompt', 'Rotate to face {facing}')
        for facing in self.facings:
            if facing == self.facing:
                continue
            interactions[f"rotate_{facing}"] = {
                'prompt': prompt.format(facing=facing),
                'disabled': no_action,
                'disabled_text': 'object.door.action_required',
            }
        return interactions

    def _friendly(self, entity, other, battle):
        if battle is not None and battle.entity_state_for(entity) and battle.entity_state_for(other):
            return battle.allies(entity, other)
        from natural20.sidekick import is_in_party_sidekick

        def party(creature):
            return creature.pc() or is_in_party_sidekick(self.session, creature)
        return party(entity) and party(other)

    def team_for(self, entity, battle=None):
        """``entity`` plus friendly creatures able to reach the handles."""
        team = [entity]
        battle_map = self.map
        if battle_map is None:
            return team
        try:
            ox, oy = battle_map.position_of(self)
        except Exception:
            return team
        feet = battle_map.feet_per_grid or 5
        reach = max(1, int(self.interact_distance) // feet)
        for creature in list(battle_map.entities.keys()):
            if creature is entity or creature.object():
                continue
            if not creature.conscious() or creature.incapacitated():
                continue
            if not self._friendly(entity, creature, battle):
                continue
            squares = battle_map.entity_squares(creature)
            if squares and min(max(abs(x - ox), abs(y - oy)) for x, y in squares) <= reach:
                team.append(creature)
        return team

    def resolve(self, entity, action, other_params, opts=None):
        opts = opts or {}
        if action and action.startswith('rotate_') and action[len('rotate_'):] in self.facings:
            facing = action[len('rotate_'):]
            battle = opts.get('battle')
            result = {
                'action': 'rotate',
                'facing': facing,
                'source': entity,
                'target': self,
                'battle': battle,
            }
            if battle is not None and self.rotate_config.get('cost', 'action') == 'action':
                result['cost'] = 'action'
            threshold = self.rotate_config.get('combined_score')
            ability = self.rotate_config.get('ability', 'strength')
            short = entity.ABILITY_SHORT_NAMES.get(ability, ability)
            if threshold is not None:
                team = self.team_for(entity, battle)
                total = sum(int(c.ability_scores.get(short) or 0) for c in team)
                if len(team) > 1 and total >= int(threshold):
                    result.update(success=True, combined_strength=total,
                                  helpers=[c.entity_uid for c in team])
                    return result
            dc = self.rotate_config.get('dc')
            if dc is None:
                result['success'] = True
                return result
            roll = entity.ability_check(short, battle)
            result.update(roll=roll, dc=int(dc), success=roll.result() >= int(dc))
            return result
        return super().resolve(entity, action, other_params, opts)

    def use(self, entity, result, session=None):
        action = result.get('action')
        session = session or self.session
        if action == 'rotate':
            event = {
                'source': entity,
                'target': self,
                'label': super().label(),
                'facing': result.get('facing'),
                'roll': result.get('roll'),
                'dc': result.get('dc'),
                'combined_strength': result.get('combined_strength'),
            }
            if not result.get('success'):
                session.event_manager.received_event({**event, 'event': 'mechanism_rotate_failed'})
                return []
            self.facing = result['facing']
            session.event_manager.received_event({**event, 'event': 'mechanism_rotated'})
            trigger_opts = {'battle': result.get('battle'), 'source': entity, 'target': self}
            results = list(self.resolve_trigger('rotate', trigger_opts) or [])
            results += list(self.resolve_trigger(f"face_{self.facing}", trigger_opts) or [])
            return results
        handled = super().use(entity, result, session)
        required = self._required_check()
        if required and action == f"{required}_check" and result.get('success'):
            self.mechanism_known = True
        return handled

    def update_state(self, state):
        if isinstance(state, str) and state.startswith('facing:'):
            facing = state.split(':', 1)[1].strip()
            if facing in self.facings:
                self.facing = facing
            return
        if state == 'mechanism_known':
            self.mechanism_known = True
            return
        super().update_state(state)

    def to_dict(self):
        data = super().to_dict()
        data['facing'] = self.facing
        data['mechanism_known'] = self.mechanism_known
        return data

    @staticmethod
    def from_dict(data):
        obj = RotatingMechanism(data['session'], None, data['properties'])
        obj.entity_uid = data['entity_uid']
        obj.is_concealed = data.get('is_concealed', False)
        obj.facing = data.get('facing', obj.facing)
        obj.mechanism_known = data.get('mechanism_known', False)
        return obj
