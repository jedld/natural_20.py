from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
import pdb
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
        super().validate(target)

        if target is None:
            target = self.target

        return len(self.errors) == 0


    def _damage(self, battle, crit=False, opts=None):
        entity = self.source
        level = 1
        if entity.level() >= 5:
            level += 1
        if entity.level() >= 11:
            level += 1
        if entity.level() >= 17:
            level += 1
        return DieRoll.roll(f"{level}d6", crit=crit, battle=battle, entity=entity, description=self.t('dice_roll.spells.burning_hands'))

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts).expected()


    def compute_hit_probability(self, battle, opts=None):
        """
        Compute the hit probability for the spell
        """
        target = self.action.target
        entity = self.source
        result = target.save_throw('dexterity', battle, { "is_magical": True })

        return 1.0 - result.prob(entity.spell_save_dc("wisdom"))

    def resolve(self, entity, battle, spell_action, _battle_map):
        results = []

        target = spell_action.target
        entity_map = self.session.map_for(entity)
        source_pos = entity_map.position_of(entity)
        squares = entity_map.squares_in_cone(source_pos, target, self.properties['range_cone'] // entity_map.feet_per_grid, require_los=True)
        entity_targets = []
        for square in squares:
            _entity = entity_map.entity_at(square[0], square[1])
            if _entity is not None:
                entity_targets.append(_entity)

        for entity_target in entity_targets:
            result = entity_target.save_throw('dexterity', battle, { "is_magical": True })
            spell_dc = entity.spell_save_dc("wisdom")
            if result < spell_dc:
                save_failed = True
            else:
                save_failed = False

            if save_failed:
                damage_roll = self._damage(battle)
                results.append(
                    {
                        'source': entity,
                        'target': entity_target,
                        'attack_name': 'burning_hands',
                        'damage_type': self.properties['damage_type'],
                        'attack_roll': None,
                        'damage_roll': damage_roll,
                        'advantage_mod': None,
                        'adv_info': None,
                        'damage': damage_roll,
                        'spell_save': result,
                        'dc': spell_dc,
                        'cover_ac': None,
                        'type': 'spell_damage',
                        'spell': self.properties
                    }
                )
            else:
                results.append(
                    {
                        'type': 'spell_miss',
                        'source': entity,
                        'target': entity_target,
                        'attack_name': 'burning_hands',
                        'attack_roll': None,
                        'advantage_mod': None,
                        'adv_info': None,
                        'spell_save': result,
                        'dc': spell_dc,
                        'cover_ac': None
                    }
                )
        return results
