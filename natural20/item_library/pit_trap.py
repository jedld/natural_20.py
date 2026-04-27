from natural20.item_library.object import Object
from natural20.event_manager import EventManager
from natural20.die_roll import DieRoll
from natural20.concern.generic_event_handler import GenericEventHandler
import pdb

# Represents a staple of DnD the concealed pit trap
class PitTrap(Object):
    DEFAULT_DISARM_DC = 15
    # If the disarm check fails by this margin or more, the trap is sprung.
    DISARM_TRIGGER_MARGIN = 5

    def __init__(self, session, map, properties):
        super().__init__(session, map, properties=properties)
        self.activated = False
        self.disarmed = False
        # Set of entity uids that have spotted the trap via passive
        # perception, an active perception/investigation check, or by
        # triggering it. Once revealed, the trap stays known to that PC.
        self.perceived_by = set()
        self.damages = properties.get('damages', [])
        self.events = properties.get('events', [])

    def to_dict(self):
        hash = super().to_dict()
        hash['activated'] = self.activated
        hash['disarmed'] = self.disarmed
        hash['perceived_by'] = sorted(self.perceived_by)
        return hash

    @staticmethod
    def from_dict(hash):
        session = hash['session']
        pit_trap = PitTrap(session, None, hash['properties'])
        pit_trap.activated = hash['activated']
        pit_trap.disarmed = hash.get('disarmed', False)
        pit_trap.perceived_by = set(hash.get('perceived_by', []) or [])
        return pit_trap

    def token_image(self):
        if self.properties.get('token_image'):
            if self.activated or self.disarmed:
                return f"objects/{self.properties.get('token_image')}"

        return None

    def area_trigger_handler(self, entity, entity_pos, is_flying):
        result = []
        if entity_pos !=  self.map.position_of(self):
            return None
        if is_flying:
            return None
        if self.disarmed:
            return None
        # Springing the trap obviously reveals it to the victim and any
        # bystanders the caller propagates the event to.
        self.mark_perceived_by(entity)
        result = []
        if not self.activated:
            if self.damages:
                for damage in self.damages:
                    result.append({
                        'source': self,
                        'target': entity,
                        'type': 'damage',
                        'attack_name': damage.get('attack_name', 'pit trap'),
                        'damage_type': damage.get('damage_type', 'piercing'),
                        'damage': DieRoll.roll(damage['damage_die'])
                    })
            else:
                result.append({
                    'source': self,
                    'target': entity,
                    'type': 'damage',
                    'attack_name': self.properties.get('attack_name', 'pit trap'),
                    'damage_type': self.properties.get('damage_type', 'piercing'),
                    'damage': DieRoll.roll(self.properties['damage_die'])
                })
            result.append({
                'source': self,
                'target': entity,
                'type': 'state',
                'params': {
                    'activated': True
                },
                'trigger': 'activate'
            })
            result.append({
                'source': self,
                'target': entity,
                'type': 'cancel_move'
            })

        return result

    def placeable(self):
        return not self.activated

    def label(self):
        if self.disarmed:
            return self.properties.get('name', 'pit trap') + ' (disarmed)'
        if not self.activated:
            return 'ground'

        return self.properties.get('name', 'pit trap')

    def passable(self, origin=None):
        return True

    def token(self):
        return ["\u02ac"]

    def concealed(self):
        # Trap stays concealed until it is sprung or has been safely
        # disarmed. After disarming everyone can see the (now harmless)
        # pit so they don't keep "discovering" it round after round.
        if self.activated or self.disarmed:
            return False
        return True

    def jump_required(self):
        return self.activated

    def setup_other_attributes(self):
        self.activated = False
        self.disarmed = False

    # ------------------------------------------------------------------
    # Disarm / inspection mechanics (5e Dexterity check w/ thieves' tools)
    # ------------------------------------------------------------------

    def disarm_dc(self):
        return self.properties.get('disarm_dc', self.DEFAULT_DISARM_DC)

    def interactable(self, entity=None):
        # Available so the engine surfaces the disarm action once the
        # trap has been spotted (concealed objects are filtered out by
        # ``Map.objects_near`` via ``can_see``).
        if self.disarmed or self.activated:
            return False
        return True

    def _entity_on_trap(self, entity):
        if entity is None or self.map is None:
            return False
        try:
            entity_pos = self.map.position_of(entity)
            trap_pos = self.map.position_of(self)
        except Exception:
            return False
        return entity_pos == trap_pos

    def _entity_uid(self, entity):
        if entity is None:
            return None
        return getattr(entity, 'entity_uid', None) or getattr(entity, 'name', None)

    def mark_perceived_by(self, entity):
        """Record that ``entity`` has noticed the trap.

        Called from ``perceived_by_entity`` whenever a fresh perception
        check succeeds, when the trap is sprung, and when the disarm
        action resolves so subsequent checks remain valid even if the
        creature steps away.
        """
        uid = self._entity_uid(entity)
        if uid is not None:
            self.perceived_by.add(uid)

    def perceived_by_entity(self, entity, admin=False):
        """Return True when ``entity`` has revealed the trap.

        A trap counts as revealed if any of the following is true:
          * the entity is admin / DM controlled,
          * the trap has been sprung or already disarmed,
          * the entity has previously been marked as having spotted it,
          * the entity can currently see it via ``Map.can_see`` (which
            honours passive perception and active perception /
            investigation rolls).
        """
        if admin or self.activated or self.disarmed:
            return True
        if entity is None:
            return False
        uid = self._entity_uid(entity)
        if uid is not None and uid in self.perceived_by:
            return True
        if self.map is not None:
            try:
                if self.map.can_see(entity, self):
                    self.mark_perceived_by(entity)
                    return True
            except Exception:
                pass
        return False

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = super().available_interactions(entity, battle, admin)
        if self.disarmed or self.activated:
            return interactions

        # Per 5e: a creature must perceive the trap (passive Perception
        # or an active Perception / Investigation check) before they can
        # attempt to disarm it.
        if not self.perceived_by_entity(entity, admin=admin):
            return interactions

        # Disarming requires a thieves' tools kit; proficiency adds the
        # bonus but is not strictly required to attempt the check.
        has_tools = bool(entity and entity.item_count('thieves_tools') > 0) or admin
        on_trap = self._entity_on_trap(entity) and not admin

        disabled = False
        disabled_text = None
        if not has_tools:
            disabled = True
            disabled_text = 'object.pit_trap.tools_required'
        elif on_trap:
            disabled = True
            disabled_text = 'object.pit_trap.cannot_disarm_from_trap'
        elif battle and entity and not entity.has_action(battle):
            disabled = True
            disabled_text = 'object.pit_trap.action_required'

        interactions['disarm'] = {
            'prompt': 'object.pit_trap.disarm',
            'disabled': disabled,
            'disabled_text': disabled_text or '',
        }
        return interactions

    def resolve(self, entity, action, other_params, opts=None):
        result = super().resolve(entity, action, other_params, opts)
        if result:
            return result

        if action == 'disarm':
            opts = opts or {}
            roll = entity.lockpick(opts.get('battle'))
            dc = self.disarm_dc()
            value = roll.result()
            if value >= dc:
                outcome = 'disarm_success'
            elif value <= dc - self.DISARM_TRIGGER_MARGIN:
                outcome = 'disarm_triggered'
            else:
                outcome = 'disarm_fail'
            return {
                'action': outcome,
                'roll': roll,
                'dc': dc,
                'cost': 'action',
            }

        return None

    def use(self, entity, result, session=None):
        results = super().use(entity, result, session) or []
        if not isinstance(results, list):
            results = []

        action = result.get('action') if isinstance(result, dict) else None
        if action not in ('disarm_success', 'disarm_fail', 'disarm_triggered'):
            return results

        roll = result.get('roll')
        dc = result.get('dc')
        roll_value = roll.result() if roll is not None else None

        if action == 'disarm_success':
            self.disarmed = True
            results.append(self.toast_message(
                entity,
                f"{entity} disarms the {self.properties.get('name', 'pit trap')} "
                f"({roll} = {roll_value} vs DC {dc})."
            ))
            if session:
                session.event_manager.received_event({
                    'source': entity,
                    'target': self,
                    'event': 'object_interaction',
                    'sub_type': 'disarm',
                    'result': 'success',
                    'roll': roll,
                    'dc': dc,
                    'reason': 'Pit trap successfully disarmed.',
                })
            return results

        if action == 'disarm_fail':
            results.append(self.toast_message(
                entity,
                f"{entity} fails to disarm the trap "
                f"({roll} = {roll_value} vs DC {dc})."
            ))
            if session:
                session.event_manager.received_event({
                    'source': entity,
                    'target': self,
                    'event': 'object_interaction',
                    'sub_type': 'disarm',
                    'result': 'failed',
                    'roll': roll,
                    'dc': dc,
                    'reason': 'Disarm attempt failed; the trap remains active.',
                })
            return results

        # disarm_triggered – fumbled the check by 5+ and sprang the trap.
        results.append(self.toast_message(
            entity,
            f"{entity} bungles the disarm and triggers the trap! "
            f"({roll} = {roll_value} vs DC {dc})"
        ))
        if session:
            session.event_manager.received_event({
                'source': entity,
                'target': self,
                'event': 'object_interaction',
                'sub_type': 'disarm',
                'result': 'triggered',
                'roll': roll,
                'dc': dc,
                'reason': 'Disarm attempt fumbled and sprang the trap.',
            })

        # Spring the trap on the disarmer as if they stepped onto it.
        trap_pos = self.map.position_of(self) if self.map is not None else None
        battle = result.get('battle') if isinstance(result, dict) else None
        trigger_results = self.area_trigger_handler(entity, trap_pos, False) or []
        for trigger in trigger_results:
            t_type = trigger.get('type')
            if t_type == 'damage':
                damage = trigger.get('damage')
                damage_value = damage.result() if hasattr(damage, 'result') else damage
                entity.take_damage(damage_value, battle=battle,
                                   damage_type=trigger.get('damage_type', 'piercing'),
                                   session=session)
            elif t_type == 'state':
                params = trigger.get('params') or {}
                if params.get('activated'):
                    self.activated = True

        return results
