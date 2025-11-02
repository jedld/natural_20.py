from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.weapons import damage_modifier, target_advantage_condition
from natural20.utils.ac_utils import effective_ac
from natural20.spell.extensions.hit_computations import AttackSpell

class EldritchBlastSpell(AttackSpell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.range = 120
        self.damage_type = "force"

    def build_map(self, orig_action):
        entity = self.source
        # Eldritch Blast gains additional beams at levels 5, 11, and 17
        num_beams = 1
        if entity.level() >= 17:
            num_beams = 4
        elif entity.level() >= 11:
            num_beams = 3
        elif entity.level() >= 5:
            num_beams = 2

        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action
        
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': num_beams,
                    'range': self.properties['range'],
                    'allow_retarget': True,
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }

    def _damage(self, battle, crit=False, opts=None):
        # Each beam does 1d10 force damage
        return DieRoll.roll("1d10", crit=crit, battle=battle, entity=self.source, description=self.t('dice_roll.spells.generic_damage', spell=self.t('spell.eldritch_blast')))

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, crit=False, opts=opts).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        targets = spell_action.target
        
        # Handle single target or multiple targets
        if not isinstance(targets, list) and not isinstance(targets, tuple):
            targets = [targets]
        
        # Determine number of beams based on character level
        num_beams = 1
        if entity.level() >= 17:
            num_beams = 4
        elif entity.level() >= 11:
            num_beams = 3
        elif entity.level() >= 5:
            num_beams = 2
        
        # If we have fewer targets than beams, repeat the last target
        while len(targets) < num_beams:
            targets.append(targets[-1] if targets else entity)
        
        result = []
        
        # Resolve each beam separately
        for i, target in enumerate(targets[:num_beams]):
            hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = evaluate_spell_attack(
                self.session, entity, target, self.properties, battle=battle, opts={"action": spell_action}
            )

            for event in events:
                result.append(event)

            if hit:
                damage_roll = self._damage(battle, crit=attack_roll.nat_20())
                result.append({
                    "source": entity,
                    "target": target,
                    "attack_name": "eldritch_blast",
                    "damage_type": self.damage_type,
                    "attack_roll": attack_roll,
                    "damage_roll": damage_roll,
                    "advantage_mod": advantage_mod,
                    "adv_info": adv_info,
                    "damage": damage_roll,
                    "cover_ac": cover_ac_adjustments,
                    "type": "spell_damage",
                    "spell": self.properties,
                    "beam": i + 1
                })
            else:
                result.append({
                    "type": "spell_miss",
                    "source": entity,
                    "target": target,
                    "attack_name": "eldritch_blast",
                    "damage_type": self.damage_type,
                    "attack_roll": attack_roll,
                    "damage_roll": None,
                    "advantage_mod": advantage_mod,
                    "adv_info": adv_info,
                    "cover_ac": cover_ac_adjustments,
                    "spell": self.properties,
                    "beam": i + 1
                })

        return result

