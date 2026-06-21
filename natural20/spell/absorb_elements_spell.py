from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


class AbsorbElementsSpell(Spell):
    """Absorb Elements: Reaction when taking elemental damage, reduce damage and retaliate."""

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.damage_type = details.get('damage_type', 'fire')
        self.counterpart = None  # The creature that damaged us

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
                    'range': self.properties.get('range', 5),
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }

    def _counter_damage(self, battle, crit=False):
        entity = self.source
        level = 1
        if entity.level() >= 5:
            level += 1
        if entity.level() >= 11:
            level += 1
        if entity.level() >= 17:
            level += 1
        return DieRoll.roll(f"2d6", crit=crit, battle=battle, entity=entity,
                            description=self.t('dice_roll.spells.absorb_elements'))

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if not target:
            return []

        damage = self._counter_damage(battle)
        return [{
            "source": entity,
            "target": target,
            "attack_name": "absorb_elements",
            "damage_type": self.damage_type,
            "attack_roll": None,
            "damage_roll": damage,
            "advantage_mod": 0,
            "adv_info": "",
            "damage": damage,
            "cover_ac": [],
            "type": "spell_damage",
            "spell": self.properties
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'spell_damage':
            return
        if battle and session is None:
            session = battle.session
        source = item.get('source')
        target = item.get('target')
        spell = item.get('spell') or {}
        if source and target:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': 'Absorb Elements',
                'source': source,
                'target': target,
            })
