import uuid

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


class ColorSprayBlindEffect:
    def __init__(self, source, target):
        self.source = source
        self.target = target
        self._id = f"color_spray_blind:{uuid.uuid4()}"

    @property
    def id(self):
        return self._id

    def __str__(self):
        return 'color_spray'

    @staticmethod
    def blinded_override(entity, opt=None):
        return True

    @staticmethod
    def start_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return
        # Schedule expiry at the end of the caster's next turn.
        entity.register_event_hook('end_of_turn', ColorSprayBlindEffect, effect=effect)

    @staticmethod
    def end_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return
        target = getattr(effect, 'target', None)
        if target is not None:
            target.dismiss_effect(effect)


class ColorSpraySpell(Spell):
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
                    'require_los': True,
                }
            ],
            'next': set_target,
        }

    def _pool_roll(self, battle, opts=None):
        if opts is None:
            opts = {}
        at_level = int(opts.get('at_level', 1) or 1)
        dice_count = 6 + max(0, at_level - 1)
        return DieRoll.roll(
            f"{dice_count}d10",
            battle=battle,
            entity=self.source,
            description='dice_roll.spells.color_spray',
        )

    def resolve(self, entity, battle, spell_action, battle_map):
        source_pos = battle_map.position_of(entity)
        target = spell_action.target
        at_level = getattr(spell_action, 'at_level', 1) or 1

        squares = battle_map.squares_in_cone(
            source_pos,
            target,
            self.properties['range_cone'] // battle_map.feet_per_grid,
            require_los=True,
        )

        entity_targets = []
        for square in squares:
            candidate = battle_map.entity_at(square[0], square[1])
            if candidate is None or candidate == entity or candidate.dead():
                continue
            if candidate in entity_targets:
                continue
            if candidate.immune_to_condition('blinded'):
                continue
            entity_targets.append(candidate)

        # 5e 2014: lowest current HP first.
        entity_targets.sort(key=lambda e: (e.hp() if e.hp() is not None else 10**9, str(e.entity_uid)))

        pool_roll = self._pool_roll(battle, opts={'at_level': at_level})
        remaining = int(pool_roll.result())
        affected = []

        for candidate in entity_targets:
            hp = candidate.hp()
            if hp is None or hp <= 0:
                continue
            if hp <= remaining:
                remaining -= hp
                affected.append(candidate)
            else:
                break

        results = [
            {
                'type': 'color_spray_cast',
                'source': entity,
                'targets': affected,
                'pool_roll': pool_roll,
                'pool_total': int(pool_roll.result()),
                'remaining': remaining,
                'spell': self.properties,
            }
        ]

        for target_entity in affected:
            results.append(
                {
                    'type': 'color_spray',
                    'source': entity,
                    'target': target_entity,
                    'spell': self.properties,
                }
            )

        return results

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item.get('type') == 'color_spray_cast':
            if session is not None:
                session.event_manager.received_event(
                    {
                        'event': 'color_spray',
                        'source': item['source'],
                        'targets': item.get('targets', []),
                        'pool_roll': item.get('pool_roll'),
                        'pool_total': item.get('pool_total'),
                        'remaining': item.get('remaining'),
                        'spell': item.get('spell'),
                    }
                )
            return

        if item.get('type') != 'color_spray':
            return

        source = item['source']
        target = item['target']
        effect = ColorSprayBlindEffect(source, target)

        source.add_casted_effect({'target': target, 'effect': effect})
        target.register_effect('blinded_override', ColorSprayBlindEffect, effect=effect, source=source)
        source.register_event_hook('start_of_turn', ColorSprayBlindEffect, effect=effect, source=source)