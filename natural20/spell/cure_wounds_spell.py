from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll

class CureWoundsSpell(Spell):
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
                    'range': self.properties['range'],
                    'target_types': ['allies', 'self']
                }
            ],
            'next': set_target
        }

    def _heal(self, battle, opts=None):
        entity = self.source
        level = 1
        if entity.level() >= 5:
            level += 1
        if entity.level() >= 11:
            level += 1
        if entity.level() >= 17:
            level += 1
        return DieRoll.roll(f"{level}d8+{entity.cleric_spell_casting_modifier()}", battle=battle, entity=entity, description=self.t('dice_roll.spells.cure_wounds'))

    def compute_hit_probability(self, battle, opts=None):
        return 1.0

    def avg_damage(self, battle, opts=None):
        return -self._heal(battle, opts).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target

        heal_roll = self._heal(battle)

        return [{
            "source": entity,
            "target": target,
            "type": "spell_heal",
            "heal_roll": heal_roll,
            "at_level": getattr(spell_action, 'at_level', 1) or 1,
            "spell": self.properties
        }]
    
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session

        if item['type'] == 'spell_heal':
            heal_value = item['heal_roll'].result()
            spell_level = item.get('at_level') or item.get('spell', {}).get('level', 1)
            bonus = 0
            source = item['source']
            target = item['target']
            if hasattr(source, 'disciple_of_life_bonus'):
                if not (hasattr(target, 'undead') and target.undead()):
                    is_construct = 'construct' in target.properties.get('race', []) if hasattr(target, 'properties') else False
                    if not is_construct:
                        bonus = source.disciple_of_life_bonus(spell_level)
            total = heal_value + bonus
            item['heal_value'] = heal_value
            item['disciple_of_life_bonus'] = bonus
            item['total_heal'] = total

            session.event_manager.received_event({'source': source,
                'heal_roll': item['heal_roll'],
                'target': target, 'value': total,
                'disciple_of_life_bonus': bonus,
                'event': 'spell_heal', 'spell': item['spell']})

            target.heal(total)