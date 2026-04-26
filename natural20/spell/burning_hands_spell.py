from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll


class BurningHandsSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_cone',
                    'num': 1,
                    'range': self.properties['range_cone'],
                    'require_los': True
                }
            ],
            'next': set_target
        }

    def validate(self, battle_map, target=None):
        super().validate(battle_map, target)

        if target is None:
            target = self.target

        return len(self.errors) == 0

    def _save_dc(self, entity):
        # Burning Hands is on the Wizard (INT) and Sorcerer (CHA) lists
        # in the 5e 2014 PHB. Use whichever of the caster's spellcasting
        # abilities yields the higher DC so multi-class / NPC casters
        # behave reasonably.
        return max(entity.spell_save_dc('intelligence'),
                   entity.spell_save_dc('charisma'))

    def _damage(self, battle, crit=False, opts=None):
        if opts is None:
            opts = {}
        # 5e 2014: 3d6 base at 1st-level slot, +1d6 per slot level above 1st.
        at_level = opts.get('at_level', getattr(self.action, 'at_level', None))
        if not at_level or at_level < 1:
            at_level = self.properties.get('level', 1) or 1
        dice = 3 + max(0, at_level - 1)
        return DieRoll.roll(f"{dice}d6", crit=crit, battle=battle, entity=self.source,
                            description=self.t('dice_roll.spells.burning_hands'))

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts=opts).expected()

    def compute_hit_probability(self, battle, opts=None):
        """
        Burning Hands always lands (half damage on save), so this returns
        the probability of dealing full damage — i.e. the chance the
        target fails its Dex save.
        """
        target = self.action.target
        entity = self.source
        result = target.save_throw('dexterity', battle, {"is_magical": True})
        return 1.0 - result.prob(self._save_dc(entity))

    def resolve(self, entity, battle, spell_action, battle_map):
        results = []

        target = spell_action.target
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', 1)

        source_pos = battle_map.position_of(entity)
        squares = battle_map.squares_in_cone(source_pos, target,
                                             self.properties['range_cone'] // battle_map.feet_per_grid,
                                             require_los=True)
        entity_targets = []
        for square in squares:
            _entity = battle_map.entity_at(square[0], square[1])
            if _entity is not None and _entity != entity and _entity not in entity_targets:
                entity_targets.append(_entity)

        spell_dc = self._save_dc(entity)

        for entity_target in entity_targets:
            # Unconscious creatures auto-fail Dex saves.
            if entity_target.conscious():
                save_result = entity_target.save_throw('dexterity', battle, {"is_magical": True})
                save_failed = save_result < spell_dc
            else:
                save_result = None
                save_failed = True

            damage_roll = self._damage(battle, opts={'at_level': at_level})

            if save_failed:
                damage_value = damage_roll
            else:
                # 5e: half damage on a successful save.
                damage_value = damage_roll.half()

            results.append({
                'source': entity,
                'target': entity_target,
                'attack_name': 'burning_hands',
                'damage_type': self.properties['damage_type'],
                'attack_roll': None,
                'damage_roll': damage_roll,
                'advantage_mod': None,
                'adv_info': None,
                'damage': damage_value,
                'spell_save': save_result,
                'save_failed': save_failed,
                'dc': spell_dc,
                'cover_ac': None,
                'type': 'spell_damage',
                'spell': self.properties
            })

        return results
