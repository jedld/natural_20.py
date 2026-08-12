from collections import OrderedDict

# Import to ensure Channel Divinity actions are registered with the class-feature registry.
from natural20.actions import turn_undead_action  # noqa: F401
from natural20.actions.wrath_of_the_storm_action import WrathOfTheStormAction  # noqa: F401

CLERIC_SPELL_SLOT_TABLE = [
    # cantrips, 1st, 2nd, 3rd ... etc

    [3, 2],  # 1
    [3, 3],  # 2
    [3, 4, 2], # 3
    [4, 4, 3], # 4
    [4, 4, 3, 2], # 5
    [4, 4, 3, 3], # 6
    [4, 4, 3, 3, 1], # 7
    [4, 4, 3, 3, 2], # 8
    [4, 4, 3, 3, 3, 1], # 9
    [5, 4, 3, 3, 3, 2], # 10
    [5, 4, 3, 3, 3, 2, 1], # 11
    [5, 4, 3, 3, 3, 2, 1], # 12
    [5, 4, 3, 3, 3, 2, 1, 1], # 13
    [5, 4, 3, 3, 3, 2, 1, 1], # 14
    [5, 4, 3, 3, 3, 2, 1, 1, 1], # 15
    [5, 4, 3, 3, 3, 2, 1, 1, 1], # 16
    [5, 4, 3, 3, 3, 2, 1, 1, 1, 1], # 17
    [5, 4, 3, 3, 3, 3, 1, 1, 1, 1], # 18
    [5, 4, 3, 3, 3, 3, 2, 1, 1, 1], # 19
    [5, 4, 3, 3, 3, 3, 2, 2, 1, 1] # 20
]


class Cleric:
    def initialize_cleric(self):
        self.spell_slots['cleric'] = self.reset_cleric_spell_slots()
        self.channel_divinity_count = 1
        self.channel_divinity_max = 1
        if self.level() >= 6:
            self.channel_divinity_max = 2
        if self.level() >= 18:
            self.channel_divinity_max = 3
        # Initialize Tempest Domain: Wrath of the Storm uses.
        self._init_wrath_of_the_storm()
        # Register reactive effect for Tempest Domain.
        if self.class_feature('wrath_of_the_storm'):
            tempest_wrath = TempestWrathEffect(self)
            self.register_event_hook('on_damage_target', tempest_wrath, 'on_damage_target')

    def channel_divinity(self):
        self.channel_divinity_count -= 1

    def has_channel_divinity(self):
        return getattr(self, 'channel_divinity_count', 0) > 0

    def divine_domain(self):
        return self.properties.get('divine_domain')

    def disciple_of_life_bonus(self, spell_level):
        """Life Domain: Disciple of Life adds 2 + spell_level to healing spells of 1st level or higher."""
        if not self.class_feature('disciple_of_life'):
            return 0
        try:
            lvl = int(spell_level or 0)
        except (TypeError, ValueError):
            return 0
        if lvl < 1:
            return 0
        return 2 + lvl

    def cleric_spell_attack_modifier(self):
        return self.proficiency_bonus() + self.wis_mod()

    def special_actions_for_cleric(self, session, battle):
        actions = []
        # if ChannelDivinityAction.can(self, battle):
        #     actions.append(ChannelDivinityAction(session, self, 'channel_divinity'))
        return actions
    
    def cleric_spell_casting_modifier(self):
        return self.wis_mod()

    def wis_mod(self):
        raise NotImplementedError

    def short_rest_for_cleric(self, battle):
        if self.channel_divinity_count < self.channel_divinity_max:
            self.channel_divinity_count += 1

    # ---- Tempest Domain: Wrath of the Storm ----

    def _init_wrath_of_the_storm(self):
        """Initialize Wrath of the Storm uses based on Wisdom modifier (minimum 1)."""
        if not self.class_feature('wrath_of_the_storm'):
            return
        wis_mod = self.wis_mod()
        self.wrath_of_the_storm_max = max(1, wis_mod)
        self.wrath_of_the_storm_uses = self.wrath_of_the_storm_max

    def long_rest_for_cleric(self, battle):
        """Restore all Wrath of the Storm uses on a long rest."""
        if not self.class_feature('wrath_of_the_storm'):
            return
        self.wrath_of_the_storm_uses = self.wrath_of_the_storm_max

    def max_slots_for_cleric(self, level):
        return CLERIC_SPELL_SLOT_TABLE[self.cleric_level - 1][level - 1] if level < len(CLERIC_SPELL_SLOT_TABLE[self.cleric_level - 1]) else 0

    def reset_cleric_spell_slots(self):
        return OrderedDict((index, slots) for index, slots in enumerate(CLERIC_SPELL_SLOT_TABLE[self.cleric_level - 1]))


class TempestWrathEffect:
    """Reaction effect for Tempest Domain: Wrath of the Storm.

    When a creature within 5 feet of the cleric that the cleric can see hits
    the cleric with a melee attack, the cleric can use their reaction to make
    the attacker make a Dexterity saving throw. On a failed save the attacker
    takes 2d8 lightning or thunder damage (cleric's choice), or half as much
    on a successful save.
    """

    def __init__(self, owner):
        self.owner = owner

    def __str__(self):
        return 'wrath_of_the_storm'

    def on_damage_target(self, entity, opts=None):
        """Handle the reactive Wrath of the Storm when the cleric is hit.

        This is called when the cleric takes damage from an attack.
        """
        if opts is None:
            opts = {}

        if entity != self.owner:
            return []

        damage_opts = opts.get('result') or opts
        if not damage_opts:
            return []

        attacker = damage_opts.get('attacker')
        if attacker is None:
            attacker = damage_opts.get('source')
        if attacker is None or attacker is self.owner:
            return []

        battle = damage_opts.get('battle')
        if battle is None:
            return []

        # Check if the cleric has charges remaining.
        if not self.owner.class_feature('wrath_of_the_storm'):
            return []
        uses = getattr(self.owner, 'wrath_of_the_storm_uses', 0)
        if uses <= 0:
            return []

        # Only melee attacks within 5 feet.
        weapon = damage_opts.get('weapon') or damage_opts.get('npc_action') or {}
        if isinstance(weapon, dict):
            weapon_type = weapon.get('type', '')
        else:
            weapon_type = str(weapon).lower() if weapon else ''
        if weapon_type == 'ranged_attack':
            return []

        # Check if the cleric has a reaction available.
        if not self.owner.has_reaction(battle):
            return []

        # Get the chosen damage type (default: lightning).
        damage_type = getattr(self.owner, '_wrath_chosen_damage_type', None)
        if damage_type not in ('lightning', 'thunder'):
            damage_type = 'lightning'

        damage_dice = getattr(self.owner, '_wrath_damage_dice', 2)

        # Resolve the saving throw and damage.
        damage_events = WrathOfTheStormAction.resolve_save_and_damage(
            self.owner.session,
            self.owner,
            attacker,
            battle,
            damage_opts,
            damage_type_override=damage_type,
        )

        return damage_events