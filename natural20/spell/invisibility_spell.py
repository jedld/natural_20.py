from natural20.spell.spell import Spell


class InvisibilitySpell(Spell):
    """Invisibility (2nd-level illusion, concentration, 1 minute).

    The target becomes invisible. The spell ends for a creature that attacks
    or casts a spell. Greater Invisibility uses the same buff without those
    break conditions.
    """

    BREAKS_ON_HOSTILE = True
    BASE_LEVEL = 2

    def build_map(self, orig_action):
        additional_targets = 0
        if orig_action.at_level > self.BASE_LEVEL:
            additional_targets = orig_action.at_level - self.BASE_LEVEL

        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1 + additional_targets,
                'range': self.properties.get('range', 30),
                'unique_targets': True,
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        targets = spell_action.target
        if not targets:
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': entity,
                'attack_name': str(self),
                'message': 'no_target',
                'spell': self.properties,
            }]
        if not isinstance(targets, list):
            targets = [targets]
        results = []
        for target in targets:
            results.append({
                'source': entity,
                'target': target,
                'type': 'invisibility',
                'spell': self.properties,
                'effect': self,
                'breaks_on_hostile': self.BREAKS_ON_HOSTILE,
            })
        return results

    @staticmethod
    def _end_for_target(entity, effect):
        if 'invisible' in getattr(entity, 'statuses', []):
            entity.statuses.remove('invisible')
        if effect is None:
            return
        for store_name in ('effects', 'entity_event_hooks'):
            store = getattr(entity, store_name, None)
            if not isinstance(store, dict):
                continue
            for key, value in list(store.items()):
                store[key] = [f for f in value if f.get('effect') is not effect]

    @staticmethod
    def attack_resolved(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        if effect is None or not getattr(effect, 'BREAKS_ON_HOSTILE', True):
            return
        InvisibilitySpell._end_for_target(entity, effect)

    @staticmethod
    def spell_cast(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        if effect is None or not getattr(effect, 'BREAKS_ON_HOSTILE', True):
            return
        InvisibilitySpell._end_for_target(entity, effect)

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'invisibility':
            return None
        if session is None:
            session = battle.session if battle else item['source'].session

        target = item['target']
        source = item['source']
        effect = item['effect']
        duration_seconds = int(effect.properties.get('duration_seconds', 60))

        source.add_casted_effect({
            'target': target,
            'effect': effect,
            'expiration': session.game_time + duration_seconds,
        })

        if source.current_concentration() != effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        target.register_effect(
            'invisible', InvisibilitySpell,
            effect=effect, source=source, duration=duration_seconds,
        )
        if getattr(effect, 'BREAKS_ON_HOSTILE', True):
            target.register_event_hook(
                'attack_resolved', InvisibilitySpell,
                effect=effect, source=source, duration=duration_seconds,
            )
            target.register_event_hook(
                'spell_cast', InvisibilitySpell,
                effect=effect, source=source, duration=duration_seconds,
            )

        if 'invisible' not in target.statuses:
            target.statuses.append('invisible')

        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': effect,
            'source': source,
            'target': target,
        })
        return target

    def dismiss(self, entity, _descriptor=None, opts=None):
        if 'invisible' in getattr(entity, 'statuses', []):
            entity.statuses.remove('invisible')


class GreaterInvisibilitySpell(InvisibilitySpell):
    """Greater Invisibility (4th-level illusion). Invisible, does not break on attack/cast."""

    BREAKS_ON_HOSTILE = False
    BASE_LEVEL = 4

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 5),
                'unique_targets': True,
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }
