from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.save_for_half import SaveForHalfMixin
from natural20.spell.extensions.save_check import SaveCheck


class BurningHandsSpell(DamageScalingMixin, SaveForHalfMixin, Spell):
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
        # 5e 2014: 3d6 base at 1st-level slot, +1d6 per slot level above 1st.
        return self._scaled_damage_roll(
            battle, "3d6", "1d6",
            opts=opts, crit=crit,
            description=self.t('dice_roll.spells.burning_hands'),
        )

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
        # AI scoring may pass a cone apex point (list/tuple) rather than a
        # single entity. Resolve to an actual creature in the area before
        # rolling a save.
        save_target = None
        if isinstance(target, (list, tuple)):
            try:
                battle_map = battle.map_for(entity) if battle else None
                if battle_map is not None:
                    source_pos = battle_map.position_of(entity)
                    squares = battle_map.squares_in_cone(
                        source_pos, target,
                        self.properties['range_cone'] // battle_map.feet_per_grid,
                        require_los=True)
                    for sq in squares:
                        candidate = battle_map.entity_at(sq[0], sq[1])
                        if candidate is not None and candidate is not entity:
                            save_target = candidate
                            break
            except Exception:
                save_target = None
        else:
            save_target = target
        if save_target is None or not hasattr(save_target, 'save_throw'):
            # No valid target to score against; treat as zero hit probability
            # so the AI doesn't pick this action over a real attack.
            return 0.0
        result = save_target.save_throw('dexterity', battle, {"is_magical": True})
        return 1.0 - result.prob(self._save_dc(entity))

    def resolve(self, entity, battle, spell_action, battle_map):
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

        return self.resolve_save_for_half(
            entity_targets,
            ability='dexterity',
            dc=spell_dc,
            damage_roll=lambda _t: self._damage(battle, opts={'at_level': at_level}),
            attack_name='burning_hands',
            damage_type=self.properties['damage_type'],
            battle=battle,
        )
