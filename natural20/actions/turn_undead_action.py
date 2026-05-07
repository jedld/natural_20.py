"""Channel Divinity: Turn Undead (Cleric L2, D&D 5e 2014 SRD).

Action: Each undead within 30 ft of the cleric that can see/hear must make a
Wisdom saving throw. On failure, the creature is *turned* for 1 minute or
until it takes damage. While turned: must spend its turns trying to move as
far away from the cleric as it can; cannot willingly move within 30 ft of
the cleric; cannot take reactions; can only Dash, or Disengage if no path
exists. (We track the status; full enforcement is opportunistic: the status
is applied and exposed to controllers/UI.)

Cost: one Channel Divinity use.
"""

from natural20.action import Action
from natural20.utils.class_feature_registry import register_class_feature


class TurnUndeadAction(Action):
    @staticmethod
    def can(entity, battle):
        if not getattr(entity, 'has_channel_divinity', None):
            return False
        if not entity.has_channel_divinity():
            return False
        if not entity.class_feature('channel_divinity_turn_undead'):
            return False
        if battle is None:
            return True
        state = battle.entity_state_for(entity)
        if not state:
            return False
        return state.get('action', 0) > 0

    def label(self):
        uses = getattr(self.source, 'channel_divinity_count', 0)
        return f"Channel Divinity: Turn Undead ({uses})"

    def __str__(self):
        return "TurnUndead"

    __repr__ = __str__

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        return TurnUndeadAction(session, source, 'channel_divinity_turn_undead').build_map()

    def resolve(self, _session, battle_map, opts=None):
        battle = (opts or {}).get('battle')
        results = []
        if battle_map is None and battle is not None:
            try:
                battle_map = battle.map_for(self.source)
            except Exception:
                battle_map = None

        targets = []
        if battle_map is not None:
            for candidate in battle_map.entities_in_range(self.source, 30):
                if candidate is self.source:
                    continue
                if candidate.dead():
                    continue
                if not (hasattr(candidate, 'undead') and candidate.undead()):
                    continue
                targets.append(candidate)

        dc = self.source.spell_save_dc('wisdom')
        if hasattr(self.source, 'cleric_level'):
            destroy_cr_cap = self._destroy_undead_cap(self.source.cleric_level)
        else:
            destroy_cr_cap = None

        for target in targets:
            roll = target.save_throw('wisdom', battle)
            success = roll.result() >= dc
            destroyed = False
            if not success and destroy_cr_cap is not None:
                cr = self._target_cr(target)
                if cr is not None and cr <= destroy_cr_cap:
                    destroyed = True
            results.append({
                'type': 'turn_undead',
                'source': self.source,
                'target': target,
                'roll': roll,
                'dc': dc,
                'success': success,
                'destroyed': destroyed,
                'battle': battle,
            })

        if not results:
            results.append({
                'type': 'turn_undead_no_targets',
                'source': self.source,
                'battle': battle,
                '_consume_resources': True,
            })
        else:
            results[0]['_consume_resources'] = True

        self.result = results
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if session is None and battle is not None:
            session = battle.session

        item_type = item.get('type')
        if item_type not in ('turn_undead', 'turn_undead_no_targets'):
            return

        source = item['source']

        if item_type == 'turn_undead':
            target = item['target']
            if item.get('destroyed'):
                if hasattr(target, 'attributes'):
                    target.attributes['hp'] = 0
                statuses = getattr(target, 'statuses', None)
                if statuses is not None and 'dead' not in statuses:
                    statuses.append('dead')
            elif not item.get('success'):
                statuses = getattr(target, 'statuses', None)
                if statuses is not None and 'turned' not in statuses:
                    statuses.append('turned')
                if hasattr(target, 'register_effect'):
                    try:
                        target.register_effect(
                            'turned',
                            TurnUndeadAction,
                            effect={'source': source, 'rounds_remaining': 10},
                            source=source,
                            duration=10,
                        )
                    except Exception:
                        pass

            if session is not None:
                session.event_manager.received_event({
                    'event': 'turn_undead',
                    'source': source,
                    'target': target,
                    'roll': item.get('roll'),
                    'dc': item.get('dc'),
                    'success': item.get('success'),
                    'destroyed': item.get('destroyed'),
                })
        elif item_type == 'turn_undead_no_targets' and session is not None:
            session.event_manager.received_event({
                'source': source,
                'event': 'turn_undead',
                'targets': [],
            })

        if item.get('_consume_resources'):
            if hasattr(source, 'channel_divinity'):
                source.channel_divinity()
            if battle is not None:
                try:
                    battle.consume(source, 'action')
                except Exception:
                    pass

    @staticmethod
    def describe(event):
        if event.get('event') != 'turn_undead':
            return ''
        source = event.get('source')
        target = event.get('target')
        src_name = source.name if source is not None else 'The cleric'
        if target is None:
            return f"{src_name} channels divine energy but no undead are within 30 ft"
        if event.get('destroyed'):
            return f"{src_name} destroys {target.name} with Turn Undead"
        if event.get('success'):
            return f"{target.name} resists {src_name}'s Turn Undead"
        return f"{target.name} is turned by {src_name}"

    @staticmethod
    def _destroy_undead_cap(cleric_level):
        """Returns max CR of undead destroyed outright; None below 5th."""
        if cleric_level >= 17:
            return 4
        if cleric_level >= 14:
            return 3
        if cleric_level >= 11:
            return 2
        if cleric_level >= 8:
            return 1
        if cleric_level >= 5:
            return 0.5
        return None

    @staticmethod
    def _target_cr(target):
        try:
            cr = target.properties.get('challenge', None)
        except Exception:
            cr = None
        if cr is None:
            return None
        if isinstance(cr, str):
            if '/' in cr:
                num, den = cr.split('/', 1)
                try:
                    return float(num) / float(den)
                except Exception:
                    return None
            try:
                return float(cr)
            except Exception:
                return None
        try:
            return float(cr)
        except Exception:
            return None


# Register with the class-feature registry so PlayerCharacter.available_actions
# surfaces this action automatically when the cleric meets the prerequisites.
register_class_feature(
    feature_id='channel_divinity_turn_undead',
    action_class=TurnUndeadAction,
    provides=lambda entity: TurnUndeadAction.can(entity, None),
)
