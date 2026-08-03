"""Mimic entity mixin — camouflage (door disguise) and adhesive mechanics.

When ``mimic_door`` is true the mimic hides behind a door-like appearance:
- ``is_concealed`` is true and ``camouflage_perception_dc`` hides it.
- The mimic reveals itself when:
  * A creature touches the door square (interact/open attempt).
  * The mimic takes damage.

Adhesive (SRD):
- On hit the target is adhered (speed reduced, attack disadvantage).
- An adhered creature can use an action for DC Strength (Athletics) to break free.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from natural20.battle import Battle
    from natural20.map import Map
    from natural20.session import Session


def _ensure_mimic_properties(properties: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure mimic-specific flags are set on the entity properties."""
    props = dict(properties)
    props.setdefault("mimic_door", False)
    props.setdefault("camouflage_perception_dc", 14)
    props.setdefault("revealed", False)
    props.setdefault("disguised_as", "door")
    return props


class Mimic:
    """Mixin for mimic-specific behaviour (camouflage + adhesive)."""

    # ------------------------------------------------------------------
    # Camouflage (door disguise)
    # ------------------------------------------------------------------

    def initialize_mimic(self) -> None:
        """Set up camouflage state when this entity is a mimic."""
        if not self.properties.get("mimic_door"):
            return
        # Start concealed — the creature looks exactly like a door.
        self.is_concealed = True
        self._camouflage_revealed = False
        self._adhered_targets: Dict[str, str] = {}  # uid -> source_label

    @property
    def camouflage_revealed(self) -> bool:
        return bool(getattr(self, "_camouflage_revealed", False))

    def camouflage_perception_dc(self) -> int:
        """Return the Perception DC to notice the mimic is not a door."""
        return int(self.properties.get("camouflage_perception_dc", 14))

    def reveal_mimic(self, battle: Optional["Battle"] = None) -> None:
        """Reveal the mimic — end camouflage state."""
        if self.camouflage_revealed:
            return
        self._camouflage_revealed = True
        self.is_concealed = False
        # Emit a message that the door is actually a monster.
        from natural20.event_manager import EventManager
        event_manager = getattr(getattr(self, "session", None), "event_manager", None)
        if event_manager is not None:
            event_manager.received_event({
                "event": "narration",
                "message": f"The '{self.label()}' IS NOT A DOOR! It is a mimic and attacks!",
                "visibility": "everyone",
            })

    def is_disguised_as_door(self) -> bool:
        """Return True when the mimic is currently camouflaged as a door."""
        return bool(
            self.properties.get("mimic_door")
            and not self.camouflage_revealed
            and not self.dead()
        )

    def trigger_mimic_attack(self, session: "Session", battle_map: "Map",
                             battle: Optional["Battle"] = None) -> None:
        """Trigger the mimic to attack and potentially start combat."""
        self.reveal_mimic(battle)

        # If there is an active battle, add the mimic to it.
        if battle is not None:
            if self not in getattr(battle, "entities", {}):
                battle.add_combatant(self, group="b")

        # Otherwise, start a battle with all adjacent PCs.
        game = getattr(self, "session", None)
        if game is None:
            game = session

        from webapp.battle_management import start_battle
        from natural20.player_character import PlayerCharacter

        # Collect nearby player characters as combatants.
        combatant_uids: List[str] = []
        for entity in list(battle_map.entities or []):
            if isinstance(entity, PlayerCharacter):
                combatant_uids.append(entity.entity_uid)

        try:
            start_battle(
                game,
                combatant_uids=combatant_uids,
                map_name=getattr(battle_map, "name", None),
            )
        except Exception:
            # Battle start may fail if already active; that's OK.
            pass

    # ------------------------------------------------------------------
    # Adhesive
    # ------------------------------------------------------------------

    def initialize_adhesive(self) -> None:
        """Set up adhesive tracking state."""
        self._adhered_targets = {}  # entity_uid -> source_label

    def adhere_target(self, target_uid: str, source_label: str,
                      adhesive_dc: int = 13) -> None:
        """Mark *target_uid* as adhered to this mimic."""
        self._adhered_targets[target_uid] = source_label

    def is_adhered(self, entity_uid: str) -> bool:
        """Return True when *entity_uid* is adhered to this mimic."""
        return entity_uid in self._adhered_targets

    def check_adhesive_release(self, entity_uid: str, roll_result: int,
                               adhesive_dc: int = 13) -> bool:
        """Check if an adhesive release attempt succeeds.

        Returns True if the creature broke free.
        """
        if entity_uid not in self._adhered_targets:
            return True  # Not adhered; nothing to release.
        if roll_result >= adhesive_dc:
            del self._adhered_targets[entity_uid]
            return True
        return False

    def adhesive_speed_penalty(self) -> int:
        """Return the speed penalty for adhered creatures (SRD: 10 ft)."""
        return int(self.properties.get("adhesive", {}).get("speed_reduce", 10))

    def get_adhered_targets(self) -> Dict[str, str]:
        """Return a copy of the adhered targets dict."""
        return dict(self._adhered_targets)

    # ------------------------------------------------------------------
    # Damage trigger (mimic attacks when damaged)
    # ------------------------------------------------------------------

    def on_mimic_takes_damage(self, damage: int, battle: Optional["Battle"] = None) -> None:
        """Called when the mimic takes damage — it attacks immediately."""
        if self.camouflage_revealed:
            return  # Already revealed; normal behaviour.
        self.reveal_mimic(battle)
        # Trigger attack with nearby PCs (battle_map will be found via session).
        game = getattr(self, "session", None)
        if game is None:
            return
        battle_map = getattr(game, "battle_map", None)
        if battle_map is None:
            # Try to get the current map from the session.
            battle_map = getattr(game, "game_session", None)
            if battle_map is not None:
                battle_map = getattr(battle_map, "current_map", None)
        if battle_map is not None:
            self.trigger_mimic_attack(game, battle_map, battle)

    # ------------------------------------------------------------------
    # Interaction trigger (mimic attacks when door is touched)
    # ------------------------------------------------------------------

    def on_mimic_interaction(self, interacted_by_uid: str,
                             session: "Session",
                             battle_map: "Map",
                             battle: Optional["Battle"] = None) -> None:
        """Called when a creature interacts with the disguised mimic."""
        if self.camouflage_revealed:
            return  # Already revealed.
        self.reveal_mimic(battle)
        self.trigger_mimic_attack(session, battle_map, battle)

    # ------------------------------------------------------------------
    # Token/image overrides for disguise
    # ------------------------------------------------------------------

    def token_image(self) -> Optional[str]:
        """Override token_image to show the disguised form while camouflaged."""
        if self.is_disguised_as_door():
            # Return the door token image instead of the mimic token.
            door_image = self.properties.get("disguised_token_image", "objects/wooden_door.png")
            return door_image
        # Use the normal mimic token.
        return super().token_image() if hasattr(super(), "token_image") else None

    def token_image_transform(self) -> Optional[Dict[str, Any]]:
        """Return CSS transform for the disguised form."""
        if self.is_disguised_as_door():
            return {
                "type": "door_transform",
            }
        return super().token_image_transform() if hasattr(super(), "token_image_transform") else None

    # ------------------------------------------------------------------
    # Opaque / passable overrides for door disguise
    # ------------------------------------------------------------------

    def opaque(self, origin=None) -> bool:
        """While disguised, the mimic blocks line of sight like a closed door."""
        if self.is_disguised_as_door():
            return True
        return super().opaque(origin=origin) if hasattr(super(), "opaque") else False

    def passable(self, origin=None) -> bool:
        """While disguised, the mimic is NOT passable (like a closed door)."""
        if self.is_disguised_as_door():
            return False
        return super().passable(origin=origin) if hasattr(super(), "passable") else False

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_mimic_dict(self) -> Dict[str, Any]:
        """Return mimic-specific state for serialization."""
        return {
            "camouflage_revealed": self.camouflage_revealed,
            "adhered_targets": self.get_adhered_targets(),
        }

    def from_mimic_dict(self, data: Dict[str, Any]) -> None:
        """Restore mimic-specific state from serialization."""
        self._camouflage_revealed = bool(data.get("camouflage_revealed", False))
        self.is_concealed = not self._camouflage_revealed and self.properties.get("mimic_door")
        self._adhered_targets = data.get("adhered_targets", {})
