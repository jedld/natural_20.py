from natural20.item_library.teleporter import Teleporter
from natural20.die_roll import DieRoll
from natural20.entity import Entity


class Chasm(Teleporter):
    """A pit/cliff edge that drops non-flying creatures to another part of the
    map (typically a lower floor) and applies configurable fall damage.

    Properties:
        target_map (str, optional): name of the linked map to drop to. If
            absent, the entity is moved to ``target_position`` on the same map.
        target_position (list[int]): [x, y] landing tile coordinates.
        fall_damage_die (str, optional): explicit damage die override
            (e.g. ``"3d6"``). Takes precedence over ``fall_distance``.
        fall_distance (int, optional): fall distance in feet. If provided
            (and no ``fall_damage_die``), damage is computed as standard
            5e fall damage: ``floor(fall_distance / 10)`` d6, capped at 20d6.
        damage_type (str, optional): defaults to ``"bludgeoning"``.
        attack_name (str, optional): defaults to ``"fall"``.
        prone_on_landing (bool, optional): default True. The fallen creature
            ends prone on the landing tile (5e rule).
    """

    def __init__(self, session, map, properties):
        # ``Teleporter`` requires ``target_position``; for a pure chasm with no
        # destination we synthesize a no-op so the parent constructor succeeds
        # and ``on_enter`` can branch on the missing target.
        if 'target_position' not in properties:
            properties = dict(properties)
            properties['target_position'] = None
        super().__init__(session, map, properties)
        self.fall_damage_die = properties.get('fall_damage_die')
        self.fall_distance = properties.get('fall_distance')
        self.fall_damage_type = properties.get('damage_type', 'bludgeoning')
        self.fall_attack_name = properties.get('attack_name', 'fall')
        self.prone_on_landing = properties.get('prone_on_landing', True)

    # ---------- damage helpers ----------
    def _damage_die_string(self):
        if self.fall_damage_die:
            return self.fall_damage_die
        if self.fall_distance:
            try:
                dice = max(0, int(self.fall_distance) // 10)
            except (TypeError, ValueError):
                dice = 0
            dice = min(dice, 20)
            if dice <= 0:
                return None
            return f"{dice}d6"
        return None

    def _apply_fall_damage(self, entity, battle):
        die_str = self._damage_die_string()
        if not die_str:
            return None
        roll = DieRoll.roll(die_str)
        damage = int(roll.result()) if hasattr(roll, 'result') else int(roll)
        session = self.session or (battle.session if battle else None)
        if session and getattr(session, 'event_manager', None):
            session.event_manager.received_event({
                'event': 'console',
                'source': self,
                'target': entity,
                'message': (
                    f"{entity.name} falls into {self.label()} and takes "
                    f"{damage} {self.fall_damage_type} damage ({die_str})."
                ),
            })
        entity.take_damage(
            damage,
            battle=battle,
            damage_type=self.fall_damage_type,
            session=session,
        )
        return damage

    # ---------- entry hook ----------
    def on_enter(self, entity: Entity, map, battle=None):
        if entity is None:
            return
        # Flyers glide over the chasm without consequence.
        if hasattr(entity, 'is_flying') and entity.is_flying():
            return

        self._apply_fall_damage(entity, battle)

        # Don't yank dead entities through the teleport hop; leave the body
        # at the source so the move loop can finish reporting the death.
        if hasattr(entity, 'dead') and entity.dead():
            return

        if self.target_position is not None:
            Teleporter.on_enter(self, entity, map, battle)

        if self.prone_on_landing and hasattr(entity, 'make_prone'):
            try:
                if not entity.prone():
                    entity.make_prone()
            except Exception:
                # ``prone()`` semantics differ across entity types; fall back
                # to the explicit setter to avoid blowing up the move loop.
                try:
                    entity.make_prone()
                except Exception:
                    pass

    # ---------- map metadata ----------
    def label(self):
        return self.properties.get('name', 'chasm')

    def passable(self, origin=None):
        return True

    def placeable(self):
        return True

    def concealed(self):
        return bool(self.properties.get('concealed', False))

    def jump_required(self):
        # Lets a flying creature glide across without "jump" prompts; ground
        # creatures crossing the boundary trigger ``on_enter`` and fall.
        return False

    # ---------- serialization ----------
    def to_dict(self):
        hash = super().to_dict()
        hash['fall_damage_die'] = self.fall_damage_die
        hash['fall_distance'] = self.fall_distance
        hash['damage_type'] = self.fall_damage_type
        hash['attack_name'] = self.fall_attack_name
        hash['prone_on_landing'] = self.prone_on_landing
        return hash

    @staticmethod
    def from_dict(hash):
        session = hash['session']
        chasm = Chasm(session, None, hash['properties'])
        chasm.entity_uid = hash['entity_uid']
        chasm.target_map = hash.get('target_map')
        chasm.target_position = hash.get('target_position')
        if 'fall_damage_die' in hash:
            chasm.fall_damage_die = hash['fall_damage_die']
        if 'fall_distance' in hash:
            chasm.fall_distance = hash['fall_distance']
        if 'damage_type' in hash:
            chasm.fall_damage_type = hash['damage_type']
        if 'attack_name' in hash:
            chasm.fall_attack_name = hash['attack_name']
        if 'prone_on_landing' in hash:
            chasm.prone_on_landing = hash['prone_on_landing']
        return chasm
