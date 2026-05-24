from natural20.spell.spell import Spell


class PolymorphSpell(Spell):
    """Polymorph: WIS save or become a beast (simplified stat swap via phase_transition)."""

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 60),
                'target_types': ['enemies', 'allies'],
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        if isinstance(target, list):
            target = target[0]
        save_roll = target.save_throw('wisdom', battle)
        dc = entity.spell_save_dc()
        if save_roll.result() >= dc:
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': target,
                'attack_name': 'polymorph',
                'spell_save': save_roll,
                'dc': dc,
            }]
        return [{
            'source': entity,
            'target': target,
            'type': 'polymorph',
            'spell': self.properties,
            'effect': self,
            'spell_save': save_roll,
            'dc': dc,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session if battle else item['source'].session
        if item.get('type') != 'polymorph':
            return None
        target = item['target']
        source = item['source']
        effect = item['effect']
        beast = effect.properties.get('beast_form', 'wolf')

        source.add_casted_effect({'target': target, 'effect': effect, 'expiration': session.game_time + 600})
        if source.current_concentration() != effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        target.properties['phase_transition'] = {
            'npc': beast,
            'keep_uid': True,
            'narration': effect.properties.get('narration', f"{target.label()} is transformed into a {beast}!"),
        }
        if 'polymorphed' not in target.statuses:
            target.statuses.append('polymorphed')

        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': effect,
            'source': source,
            'target': target,
        })
        # Transform immediately for dramatic effect (HP becomes beast HP).
        target._maybe_phase_transition(battle=battle)
        return target
