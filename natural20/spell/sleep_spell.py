from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


def _entities_in_squares(battle_map, squares, source):
    targets = []
    for x, y in squares:
        for entity in battle_map.entities_at(x, y):
            if entity is not source and entity not in targets:
                targets.append(entity)
    return targets


class SleepSpell(Spell):
    """Sleep (1st-level enchantment, 5e 2014).

    Roll 5d8 HP pool; creatures in a 20-ft radius fall unconscious in ascending
    current HP order. Undead and charm-immune creatures are unaffected.
    """

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_radius',
                'num': 1,
                'range': self.properties.get('range', 90),
                'radius': self.properties.get('radius', 20),
            }],
            'next': set_target,
        }

    def _pool_roll(self, battle, *, at_level: int):
        dice_count = 5 + max(0, int(at_level) - 1) * 2
        return DieRoll.roll(
            f'{dice_count}d8',
            battle=battle,
            entity=self.source,
            description='dice_roll.spells.sleep',
        )

    def _eligible_targets(self, entity, battle_map, center):
        squares = battle_map.squares_in_radius(
            (int(center[0]), int(center[1])),
            self.properties.get('radius', 20),
            require_los=self.properties.get('require_los', False),
        )
        entity_targets = []
        for candidate in _entities_in_squares(battle_map, squares, entity):
            if candidate.dead():
                continue
            if candidate.unconscious():
                continue
            if candidate.undead():
                continue
            if candidate.immune_to_condition('charmed'):
                continue
            if candidate in entity_targets:
                continue
            entity_targets.append(candidate)

        entity_targets.sort(
            key=lambda e: (e.hp() if e.hp() is not None else 10**9, str(e.entity_uid)),
        )
        return entity_targets

    def resolve(self, entity, battle, spell_action, battle_map):
        at_level = getattr(spell_action, 'at_level', None) or self.properties.get('level', 1) or 1
        center = spell_action.target
        pool_roll = self._pool_roll(battle, at_level=int(at_level))
        remaining = int(pool_roll.result())
        affected = []

        for candidate in self._eligible_targets(entity, battle_map, center):
            hp = candidate.hp()
            if hp is None or hp <= 0:
                continue
            if hp <= remaining:
                remaining -= hp
                affected.append(candidate)
            else:
                break

        results = [{
            'type': 'sleep_cast',
            'source': entity,
            'targets': affected,
            'pool_roll': pool_roll,
            'pool_total': int(pool_roll.result()),
            'remaining': remaining,
            'spell': self.properties,
        }]
        for target_entity in affected:
            results.append({
                'type': 'sleep',
                'source': entity,
                'target': target_entity,
                'spell': self.properties,
                'effect': self,
            })
        return results

    @staticmethod
    def wake_sleeping_target(target, *, source=None, battle=None, session=None):
        """Dismiss sleep when the sleeper takes damage or is shaken awake."""
        if target is None:
            return False
        woke = False
        for effect_list in list((getattr(target, 'effects', {}) or {}).values()):
            for descriptor in list(effect_list):
                handler = descriptor.get('handler')
                effect = descriptor.get('effect')
                if handler is SleepSpell and effect is not None:
                    target.remove_effect(effect)
                    woke = True
        if woke and session is not None:
            session.event_manager.received_event({
                'event': 'sleep_wake',
                'source': source,
                'target': target,
            })
        return woke

    @staticmethod
    def on_damage(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        if effect is None:
            return
        session = getattr(entity, 'session', None)
        SleepSpell.wake_sleeping_target(entity, session=session)

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item.get('type') == 'sleep_cast':
            if session is not None:
                session.event_manager.received_event({
                    'event': 'sleep',
                    'source': item['source'],
                    'targets': item.get('targets', []),
                    'pool_roll': item.get('pool_roll'),
                    'pool_total': item.get('pool_total'),
                    'remaining': item.get('remaining'),
                    'spell': item.get('spell'),
                })
            return

        if item.get('type') != 'sleep':
            return None

        source = item['source']
        target = item['target']
        effect = item['effect']
        duration_seconds = int((item.get('spell') or {}).get('duration_seconds', 60))

        source.add_casted_effect({
            'target': target,
            'effect': effect,
            'expiration': session.game_time + duration_seconds if session else None,
        })

        target.register_effect(
            'sleep', SleepSpell,
            effect=effect, source=source, duration=duration_seconds,
        )
        target.register_event_hook(
            'damage', SleepSpell, method_name='on_damage',
            effect=effect, source=source, duration=duration_seconds,
        )

        for status in ('sleep', 'unconscious', 'incapacitated'):
            if status not in target.statuses:
                target.statuses.append(status)

        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_debuff',
                'spell': effect,
                'source': source,
                'target': target,
            })
        return target

    def dismiss(self, entity, _descriptor=None, opts=None):
        for status in ('sleep', 'unconscious'):
            if status in getattr(entity, 'statuses', []):
                entity.statuses.remove(status)
        if 'incapacitated' in getattr(entity, 'statuses', []):
            entity.statuses.remove('incapacitated')

    @property
    def id(self):
        return self.properties.get('id') or 'sleep'
