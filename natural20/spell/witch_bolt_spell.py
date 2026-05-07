import uuid

from natural20.die_roll import DieRoll
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.utils.spell_attack_util import evaluate_spell_attack


class WitchBoltEffect:
    DURATION_SECONDS = 60

    def __init__(self, source, target, battle, spell_properties=None):
        self.source = source
        self.target = target
        self.battle = battle
        self.spell_properties = spell_properties or {}
        self._id = f"witch_bolt:{uuid.uuid4()}"
        self.sustained_this_turn = False

    @property
    def id(self):
        return self._id

    def __str__(self):
        return 'witch_bolt'

    def is_link_valid(self):
        if self.source is None or self.target is None:
            return False
        if self.target.dead() or self.source.dead() or self.source.unconscious():
            return False
        battle = self.battle
        if battle is None:
            return True
        battle_map = battle.map_for(self.source)
        if battle_map is None:
            return False

        max_range_ft = int(self.spell_properties.get('range', 30) or 30)
        feet_per_grid = int(getattr(battle_map, 'feet_per_grid', 5) or 5)
        distance_ft = battle_map.distance(self.source, self.target) * feet_per_grid
        if distance_ft > max_range_ft:
            return False

        # The 2014 spell ends if the target has total cover from the caster.
        if not battle_map.can_see(self.source, self.target):
            return False

        return True

    @staticmethod
    def start_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return
        effect.sustained_this_turn = False

        if not effect.is_link_valid() or entity.current_concentration() is not effect:
            entity.dismiss_effect(effect)
            return

        entity.register_event_hook('end_of_turn', WitchBoltEffect, effect=effect)

    @staticmethod
    def end_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return

        if entity.current_concentration() is not effect:
            entity.dismiss_effect(effect)
            return

        if not effect.is_link_valid():
            entity.dismiss_effect(effect)
            return

        battle = effect.battle
        if battle is None:
            return
        state = battle.entity_state_for(entity)
        if state is None:
            return

        # RAW (2014): using your action for anything except sustaining the
        # bolt ends the spell.
        if int(state.get('action', 0) or 0) <= 0 and not effect.sustained_this_turn:
            entity.dismiss_effect(effect)


class WitchBoltSpell(AttackSpell):
    def build_map(self, orig_action):
        def set_target(target):
            if not target:
                raise ValueError("Invalid target")

            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies'],
                }
            ],
            'next': set_target,
        }

    def _initial_damage(self, battle, crit=False, opts=None):
        if opts is None:
            opts = {}
        at_level = int(opts.get('at_level', 1) or 1)
        dice_count = 1 + max(0, at_level - 1)
        return DieRoll.roll(
            f"{dice_count}d12",
            crit=crit,
            battle=battle,
            entity=self.source,
            description="dice_roll.spells.witch_bolt",
        )

    def avg_damage(self, battle, opts=None):
        return self._initial_damage(battle, opts=opts).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        result = []
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = evaluate_spell_attack(
            self.session,
            entity,
            target,
            self.properties,
            battle=battle,
            opts={"action": spell_action},
        )
        for event in events:
            result.append(event)

        if hit:
            damage_roll = self._initial_damage(
                battle,
                crit=attack_roll.nat_20(),
                opts={"at_level": spell_action.at_level},
            )
            effect = WitchBoltEffect(entity, target, battle, spell_properties=self.properties)
            result.extend(
                [
                    {
                        'source': entity,
                        'target': target,
                        'attack_name': "spell.witch_bolt",
                        'damage_type': self.properties['damage_type'],
                        'attack_roll': attack_roll,
                        'damage_roll': damage_roll,
                        'advantage_mod': advantage_mod,
                        'adv_info': adv_info,
                        'damage': damage_roll,
                        'cover_ac': cover_ac_adjustments,
                        'type': 'spell_damage',
                        'spell': self.properties,
                    },
                    {
                        'type': 'witch_bolt',
                        'source': entity,
                        'target': target,
                        'effect': effect,
                        'spell': self.properties,
                    },
                ]
            )
        else:
            result.append(
                {
                    'source': entity,
                    'target': target,
                    'attack_name': "spell.witch_bolt",
                    'attack_roll': attack_roll,
                    'advantage_mod': advantage_mod,
                    'adv_info': adv_info,
                    'cover_ac': cover_ac_adjustments,
                    'type': 'spell_miss',
                    'spell': self.properties,
                }
            )

        return result

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'witch_bolt':
            return

        if battle and session is None:
            session = battle.session

        source = item['source']
        target = item['target']
        effect = item['effect']

        source.dismiss_effect('witch_bolt')

        if session is not None:
            source.add_casted_effect(
                {
                    'target': target,
                    'effect': effect,
                    'expiration': session.game_time + WitchBoltEffect.DURATION_SECONDS,
                }
            )

        source.register_effect(
            'witch_bolt',
            WitchBoltSpell,
            effect=effect,
            source=source,
            duration=WitchBoltEffect.DURATION_SECONDS,
        )
        source.register_event_hook(
            'start_of_turn',
            WitchBoltEffect,
            effect=effect,
            source=source,
            duration=WitchBoltEffect.DURATION_SECONDS,
        )

        if source.current_concentration() is not effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        if session is not None:
            session.event_manager.received_event(
                {
                    'event': 'witch_bolt',
                    'source': source,
                    'target': target,
                }
            )
