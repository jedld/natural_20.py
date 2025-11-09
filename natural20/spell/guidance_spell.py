from natural20.spell.spell import Spell


class GuidanceSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)

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
        guidance_spell = GuidanceSpell(data['session'], data['source'], data['name'], data['properties'])
        guidance_spell.action = data['action']
        return guidance_spell

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        rng = self.properties.get('range', 5)
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': rng,
                    'unique_targets': True,
                    'target_types': ['allies', 'self']
                }
            ],
            'next': set_target
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        targets = spell_action.target
        if not isinstance(targets, list):
            targets = [targets]
        results = []
        for target in targets:
            results.append({
                'source': entity,
                'target': target,
                'type': 'guidance',
                'spell': self.properties,
                'effect': self
            })
        return results

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'guidance':
            return None

        source = item.get('source')
        target = item.get('target')
        effect = item.get('effect')

        if session is None:
            if battle:
                session = battle.session
            elif source:
                session = source.session

        duration = 60  # 1 minute concentration

        if source:
            source.add_casted_effect({
                'target': target,
                'effect': effect,
                'expiration': session.game_time + duration if session else None
            })

            if source.current_concentration() != effect:
                source.concentration_on(effect)

        if target:
            target.register_effect('guidance', GuidanceSpell, effect=effect, source=source, duration=duration)

        if session and session.event_manager:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': source,
                'target': target
            })

        return target
