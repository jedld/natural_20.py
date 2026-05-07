from natural20.die_roll import DieRoll
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.utils.spell_attack_util import evaluate_spell_attack


class ChromaticOrbSpell(AttackSpell):
    DAMAGE_TYPES = ("acid", "cold", "fire", "lightning", "poison", "thunder")

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.chosen_damage_type = details.get("damage_type", "acid")

    def clone(self):
        spell = super().clone()
        spell.chosen_damage_type = self.chosen_damage_type
        return spell

    def build_map(self, orig_action):
        choices = [[damage_type.capitalize(), damage_type] for damage_type in self.DAMAGE_TYPES]

        def set_damage_type(choice):
            damage_type = str(choice).lower()
            if damage_type not in self.DAMAGE_TYPES:
                raise ValueError(f"Invalid chromatic orb damage type: {choice}")

            action = orig_action.clone()
            action.spell_action.chosen_damage_type = damage_type

            def set_target(target):
                action2 = action.clone()
                action2.target = target
                return action2

            return {
                'param': [
                    {
                        'type': 'select_target',
                        'num': 1,
                        'range': self.properties['range'],
                        'target_types': ['enemies']
                    }
                ],
                'next': set_target
            }

        return {
            'param': [
                {
                    'type': 'select_choice',
                    'choices': choices,
                    'num': 1
                }
            ],
            'next': set_damage_type
        }

    def _damage(self, battle, crit=False, opts=None):
        if opts is None:
            opts = {}

        at_level = int(opts.get('at_level', 1) or 1)
        dice_count = 3 + max(0, at_level - 1)
        return DieRoll.roll(
            f"{dice_count}d8",
            crit=crit,
            battle=battle,
            entity=self.source,
            description="dice_roll.spells.chromatic_orb"
        )

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts=opts).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        result = []
        target = spell_action.target
        damage_type = getattr(spell_action.spell_action, 'chosen_damage_type', self.chosen_damage_type)
        if damage_type not in self.DAMAGE_TYPES:
            damage_type = self.chosen_damage_type

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = evaluate_spell_attack(
            self.session,
            entity,
            target,
            self.properties,
            battle=battle,
            opts={"action": spell_action}
        )

        for event in events:
            result.append(event)

        spell_payload = dict(self.properties)
        spell_payload['damage_type'] = damage_type

        if hit:
            damage_roll = self._damage(
                battle,
                crit=attack_roll.nat_20(),
                opts={"at_level": spell_action.at_level}
            )
            result.append({
                'source': entity,
                'target': target,
                'attack_name': "spell.chromatic_orb",
                'damage_type': damage_type,
                'attack_roll': attack_roll,
                'damage_roll': damage_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'damage': damage_roll,
                'cover_ac': cover_ac_adjustments,
                'type': 'spell_damage',
                'spell': spell_payload
            })
        else:
            result.append({
                'source': entity,
                'target': target,
                'attack_name': "spell.chromatic_orb",
                'damage_type': damage_type,
                'attack_roll': attack_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'cover_ac': cover_ac_adjustments,
                'type': 'spell_miss',
                'spell': spell_payload
            })

        return result