from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


def _spell_dc(entity):
    return entity.spell_save_dc('wisdom')


class HoldPersonSpell(Spell):
    """Hold Person: Wisdom save or be paralyzed. Paralyzed creatures automatically fail saves and attack rolls."""

    TARGET_TYPES = ['enemies']

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
                    'target_types': self.TARGET_TYPES
                }
            ],
            'next': set_target
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if not target:
            return [{
                "type": "spell_miss",
                "source": entity,
                "target": entity,
                "attack_name": "hold_person",
                "damage_type": None,
                "attack_roll": None,
                "damage_roll": None,
                "advantage_mod": 0,
                "adv_info": "",
                "cover_ac": [],
                "spell": self.properties
            }]

        # Target makes a Wisdom saving throw
        dc = _spell_dc(entity)
        save_roll = DieRoll.roll(f"1d20 + {target.bonuses().get('wis', 0)}",
                                  battle=battle, entity=target,
                                  description=f"{target.name} Wisdom save vs Hold Person")
        save_bonus = target.bonuses().get('wis', 0)
        total_save = save_roll.total

        result = []
        if total_save >= dc:
            # Target succeeds
            result.extend([{
                "type": "spell_resist",
                "source": entity,
                "target": target,
                "attack_name": "hold_person",
                "damage_type": None,
                "save_roll": save_roll,
                "save_dc": dc,
                "save_bonus": save_bonus,
                "spell": self.properties
            }])
        else:
            # Target is paralyzed
            result.extend([{
                "type": "spell_effect",
                "source": entity,
                "target": target,
                "attack_name": "hold_person",
                "damage_type": None,
                "save_roll": save_roll,
                "save_dc": dc,
                "save_bonus": save_bonus,
                "spell": self.properties,
                "status": "paralyzed",
                "status_duration": self.properties.get('duration_seconds', 600)
            }])

        return result

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'spell_effect':
            return
        if battle and session is None:
            session = battle.session
        target = item.get('target')
        source = item.get('source')
        status = item.get('status', 'paralyzed')
        duration = item.get('status_duration', 600)

        if target and hasattr(target, 'statuses'):
            if status not in target.statuses:
                target.statuses.append(status)

        if target:
            target.register_effect('hold_person', HoldPersonSpell,
                                   effect='paralyzed', source=source, duration=duration)

        if session:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': 'Hold Person',
                'source': source,
                'target': target,
            })
