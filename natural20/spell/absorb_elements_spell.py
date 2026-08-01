from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell

ELEMENTAL_DAMAGE_TYPES = frozenset({'acid', 'cold', 'fire', 'lightning', 'thunder'})
ABSORB_ELEMENTS_ROUND_SECONDS = 6


class AbsorbElementsMeleeEffect:
    """First melee hit after Absorb Elements deals extra elemental damage."""

    def __init__(self, owner, damage_type: str, dice_count: int, spell_properties):
        self.owner = owner
        self.damage_type = damage_type
        self.dice_count = max(1, int(dice_count or 1))
        self.spell_properties = spell_properties or {}

    def __str__(self):
        return 'absorb_elements'

    def on_attack_hit(self, entity, opts=None):
        opts = opts or {}
        if entity is not self.owner:
            return []

        hit_result = opts.get('result') or {}
        if not hit_result.get('hit?'):
            return []

        if hit_result.get('thrown'):
            return []

        weapon = hit_result.get('weapon') or {}
        if weapon.get('type') == 'ranged_attack':
            return []

        target = hit_result.get('target')
        if target is None:
            return []

        battle = hit_result.get('battle')
        damage_roll = DieRoll.roll(
            f"{self.dice_count}d6",
            crit=bool(hit_result.get('attack_roll') and hit_result['attack_roll'].nat_20()),
            battle=battle,
            entity=entity,
            description='dice_roll.spells.absorb_elements',
        )

        entity.dismiss_effect(self)
        if hasattr(entity, 'statuses') and 'absorb_elements' in entity.statuses:
            entity.statuses.remove('absorb_elements')

        return [{
            'source': entity,
            'target': target,
            'attack_name': 'absorb_elements',
            'damage_type': self.damage_type,
            'attack_roll': None,
            'damage_roll': damage_roll,
            'advantage_mod': 0,
            'adv_info': '',
            'damage': damage_roll,
            'cover_ac': [],
            'type': 'spell_damage',
            'spell': self.spell_properties,
            'source_spell': 'absorb_elements',
        }]


class AbsorbElementsSpell(Spell):
    """Absorb Elements (1st-level abjuration, reaction).

    Cast on yourself when you take acid, cold, fire, lightning, or thunder
    damage. You gain resistance to that type until the start of your next
    turn, mitigating the triggering hit, and your first melee hit on your
    next turn deals extra damage of that type.
    """

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.chosen_damage_type = details.get('damage_type')

    def build_map(self, orig_action):
        return None

    @staticmethod
    def elemental_damage_type(damage_opts=None, item=None):
        damage_opts = damage_opts or {}
        item = item or {}
        damage_type = (
            damage_opts.get('damage_type')
            or item.get('damage_type')
            or ''
        )
        damage_type = str(damage_type).strip().lower()
        if damage_type in ELEMENTAL_DAMAGE_TYPES:
            return damage_type
        return None

    @staticmethod
    def is_absorb_elements(spell_details, spell_name=None):
        if not spell_details:
            return False
        spell_id = str(spell_details.get('id') or spell_name or '').strip().lower()
        spell_class = str(spell_details.get('spell_class') or '').strip().lower()
        return spell_id == 'absorb_elements' or spell_class.endswith('absorbelements')

    def _melee_bonus_dice(self, at_level=None):
        level = at_level
        if level is None and self.action is not None:
            level = getattr(self.action, 'at_level', None)
        if level is None:
            level = self.properties.get('level', 1)
        return max(1, int(level or 1))

    def resolve(self, entity, battle, spell_action, battle_map):
        damage_type = (
            getattr(spell_action, 'trigger_damage_type', None)
            or self.chosen_damage_type
            or self.properties.get('damage_type')
        )
        damage_type = str(damage_type or 'fire').strip().lower()
        if damage_type not in ELEMENTAL_DAMAGE_TYPES:
            return []

        heal_amount = int(getattr(spell_action, 'trigger_heal_amount', 0) or 0)
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', 1)

        return [{
            'type': 'absorb_elements',
            'source': entity,
            'target': entity,
            'effect': self,
            'spell': self.properties,
            'damage_type': damage_type,
            'at_level': at_level,
            'heal_amount': heal_amount,
            'as_reaction': True,
        }]

    @staticmethod
    def resistance_override(entity, opts=None):
        opts = opts or {}
        base = list(opts.get('value') or [])
        effect = opts.get('effect')
        damage_type = None
        if effect is not None:
            damage_type = getattr(effect, 'chosen_damage_type', None)
            if not damage_type and hasattr(effect, 'properties'):
                damage_type = effect.properties.get('damage_type')
        damage_type = str(damage_type or '').strip().lower()
        if damage_type and damage_type not in base:
            base.append(damage_type)
        return base

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'absorb_elements':
            return

        if battle and session is None:
            session = battle.session
        if session is None:
            return

        target = item.get('target')
        effect = item.get('effect')
        spell = item.get('spell') or {}
        damage_type = item.get('damage_type')
        at_level = item.get('at_level', spell.get('level', 1))

        if effect is not None and damage_type:
            effect.chosen_damage_type = damage_type

        if target is not None and effect is not None:
            duration = spell.get('duration_seconds', ABSORB_ELEMENTS_ROUND_SECONDS)
            target.register_effect(
                'resistance_override',
                AbsorbElementsSpell,
                effect=effect,
                source=item.get('source'),
                duration=duration,
            )
            melee_effect = AbsorbElementsMeleeEffect(
                target,
                damage_type,
                effect._melee_bonus_dice(at_level) if hasattr(effect, '_melee_bonus_dice') else max(1, int(at_level or 1)),
                spell,
            )
            target.register_event_hook(
                'on_attack_hit',
                melee_effect,
                'on_attack_hit',
                source=item.get('source'),
                effect=melee_effect,
                duration=duration,
            )
            if 'absorb_elements' not in target.statuses:
                target.statuses.append('absorb_elements')

        heal_amount = int(item.get('heal_amount') or 0)
        if target is not None and heal_amount > 0 and item.get('apply_heal'):
            target.heal(heal_amount)

        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': spell.get('label') or spell.get('name') or 'Absorb Elements',
            'source': item.get('source'),
            'target': target,
        })
