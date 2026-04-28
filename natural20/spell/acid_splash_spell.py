from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll


class AcidSplashSpell(Spell):
    """Acid Splash (conjuration cantrip).

    Choose 1 or 2 creatures within range; if two, they must be within 5 ft of
    each other. Each target makes a DEX save or takes 1d6 acid damage.
    Damage scales at character levels 5/11/17.
    """

    def to_dict(self):
        return {
            'name': self.name,
            'action': self.action,
            'session': self.session,
            'properties': self.properties,
            'source': self.source.entity_uid,
        }

    @staticmethod
    def from_dict(data):
        spell = AcidSplashSpell(data['session'], data['source'], data['name'], data['properties'])
        spell.action = data['action']
        return spell

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 2,
                    'range': self.properties['range'],
                    'unique_targets': True,
                    'target_types': ['enemies'],
                    'min': 1,
                }
            ],
            'next': set_target,
        }

    def _dice_count(self):
        level = self.source.level()
        n = 1
        if level >= 5:
            n += 1
        if level >= 11:
            n += 1
        if level >= 17:
            n += 1
        return n

    def _damage(self, battle, crit=False):
        n = self._dice_count()
        return DieRoll.roll(
            f"{n}d6",
            crit=crit,
            battle=battle,
            entity=self.source,
            description='dice_roll.spells.acid_splash',
        )

    def avg_damage(self, battle, opts=None):
        return self._damage(battle).expected()

    def compute_hit_probability(self, battle, opts=None):
        target = self.action.target if self.action else None
        if isinstance(target, list):
            target = target[0] if target else None
        if target is None:
            return 0.0
        result = target.save_throw('dexterity', battle, {'is_magical': True})
        return 1.0 - result.prob(self.source.spell_save_dc('intelligence'))

    def resolve(self, entity, battle, spell_action, _battle_map):
        targets = spell_action.target
        if not isinstance(targets, list):
            targets = [targets]

        results = []
        spell_dc = entity.spell_save_dc('intelligence')
        for target in targets:
            save = target.save_throw('dexterity', battle, {'is_magical': True})
            if save < spell_dc:
                damage_roll = self._damage(battle)
                results.append({
                    'source': entity,
                    'target': target,
                    'attack_name': 'acid_splash',
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': None,
                    'damage_roll': damage_roll,
                    'advantage_mod': None,
                    'adv_info': None,
                    'damage': damage_roll,
                    'spell_save': save,
                    'dc': spell_dc,
                    'cover_ac': None,
                    'type': 'spell_damage',
                    'spell': self.properties,
                })
            else:
                results.append({
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': 'acid_splash',
                    'attack_roll': None,
                    'advantage_mod': None,
                    'adv_info': None,
                    'spell_save': save,
                    'dc': spell_dc,
                    'cover_ac': None,
                })
        return results
