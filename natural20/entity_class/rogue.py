# typed: false
class Rogue:
    def __init__(self):
        self.rogue_level = None

    def initialize_rogue(self):
        if self.class_feature('martial_adept') or self.properties.get('superiority_dice'):
            max_dice = int(self.properties.get('superiority_dice', 1) or 1)
            self.register_resource(
                'superiority_dice',
                max_dice,
                restore_on='short_rest',
            )

    def superiority_die(self):
        return self.properties.get('superiority_die', '1d6')

    def maneuver_save_dc(self):
        return 8 + self.proficiency_bonus() + max(self.str_mod(), self.dex_mod())

    def has_maneuver(self, maneuver):
        return maneuver in (self.properties.get('maneuvers') or [])

    def sneak_attack_level(self):
        levels = [
            "1d6", "1d6",
            "2d6", "2d6",
            "3d6", "3d6",
            "4d6", "4d6",
            "5d6", "5d6",
            "6d6", "6d6",
            "7d6", "7d6",
            "8d6", "8d6",
            "9d6", "9d6",
            "10d6", "10d6",
        ]
        return levels[self.rogue_level]

    def sneak_attack_available(self, battle):
        if battle is None:
            return True
        state = battle.entity_state_for(self)
        if not state:
            return True
        current = battle.current_turn()
        turn_marker = (
            getattr(current, 'entity_uid', None),
            getattr(battle, 'round', 0),
        )
        return state.get('sneak_attack_turn') != turn_marker

    def mark_sneak_attack_used(self, battle):
        if battle is None:
            return
        state = battle.entity_state_for(self)
        if not state:
            return
        current = battle.current_turn()
        state['sneak_attack_turn'] = (
            getattr(current, 'entity_uid', None),
            getattr(battle, 'round', 0),
        )

    def can_sneak_attack(self, battle, target, weapon, advantage=False,
                         disadvantage=False):
        if not self.class_feature('sneak_attack'):
            return False
        if not self.sneak_attack_available(battle):
            return False

        weapon_properties = weapon.get('properties') or []
        eligible_weapon = (
            'finesse' in weapon_properties
            or weapon.get('type') == 'ranged_attack'
        )
        if not eligible_weapon:
            return False
        if disadvantage:
            return False
        if advantage:
            return True
        if battle and battle.enemy_in_melee_range(target, [self]):
            return True
        return self._rakish_audacity_sneak_attack(battle, target, weapon)

    def _rakish_audacity_sneak_attack(self, battle, target, weapon):
        if not battle or not self.class_feature('rakish_audacity'):
            return False
        if weapon.get('type') != 'melee_attack':
            return False

        battle_map = battle.map_for(self)
        if not battle_map or target not in battle_map.entities:
            return False
        if battle_map.distance(self, target) * battle_map.feet_per_grid > 5:
            return False

        for entity in battle.entities.keys():
            if entity in (self, target):
                continue
            if entity not in battle_map.entities:
                continue
            if not entity.conscious():
                continue
            if battle_map.distance(self, entity) * battle_map.feet_per_grid <= 5:
                return False
        return True

    def special_actions_for_rogue(self, session, battle):
        return []
