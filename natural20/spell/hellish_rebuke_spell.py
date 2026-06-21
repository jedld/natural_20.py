from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll


class HellishRebukeSpell(Spell):
    """Hellish Rebuke (1st level evocation, casting time: 1 reaction).

    Cast as a reaction in response to taking damage from a creature you
    can see within 60 ft. The triggering creature must make a Dexterity
    save: 2d10 fire damage on a failed save, or half as much on a success.
    Damage increases by 1d10 per spell-slot level above 1st.
    """

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties.get('range', 60),
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }

    def _damage(self, battle, crit=False, opts=None):
        if opts is None:
            opts = {}
        at_level = opts.get('at_level', getattr(self.action, 'at_level', 1) or 1)
        if at_level < 1:
            at_level = 1
        # 2d10 base; +1d10 for every slot above 1st.
        dice = 2 + max(0, at_level - 1)
        return DieRoll.roll(
            f"{dice}d10",
            crit=crit,
            battle=battle,
            entity=self.source,
            description=self.t(
                'dice_roll.spells.generic_damage',
                spell=self.t('spell.hellish_rebuke') if hasattr(self, 't') else 'Hellish Rebuke'
            ) if hasattr(self, 't') else 'dice_roll.spells.hellish_rebuke',
        )

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts=opts).expected()

    def compute_hit_probability(self, battle, opts=None):
        target = self.action.target
        entity = self.source
        result = target.save_throw('dexterity', battle, {'is_magical': True})
        # All-or-half: even on save we still deal half damage, so the spell
        # always lands. Treat hit_probability as 1.0 minus the save chance
        # to mirror burning_hands' convention for AI heuristics.
        return 1.0 - result.prob(self._spell_save_dc(entity))

    def _spell_save_dc(self, entity):
        # Tieflings cast Hellish Rebuke as an innate (Charisma) spell;
        # warlocks also use Charisma. Default to charisma when available
        # and fall back to whatever the entity's primary casting ability is.
        return entity.spell_save_dc('charisma')

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', 1)

        save = target.save_throw('dexterity', battle, {'is_magical': True})
        dc = self._spell_save_dc(entity)
        damage_roll = self._damage(battle, opts={'at_level': at_level})

        if target.class_feature('evasion'):
            damage = damage_roll.half() if save < dc else 0
        elif save < dc:
            damage = damage_roll
        else:
            damage = damage_roll.half()

        return [{
            'source': entity,
            'target': target,
            'attack_name': 'hellish_rebuke',
            'damage_type': self.properties.get('damage_type', 'fire'),
            'attack_roll': None,
            'damage_roll': damage_roll,
            'advantage_mod': None,
            'adv_info': None,
            'damage': damage,
            'spell_save': save,
            'dc': dc,
            'cover_ac': None,
            'as_reaction': True,
            'type': 'spell_damage',
            'spell': self.properties,
        }]
