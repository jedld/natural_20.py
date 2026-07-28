from natural20.spell.spell import Spell


class SlowSpell(Spell):
    """Slow (2014): 40-ft cube, WIS save or halved speed, -2 AC, no reactions."""

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_square',
                'num': 1,
                'range': self.properties.get('range', 120),
            }],
            'next': set_target,
        }

    def _affected_squares(self, battle_map, center):
        radius_ft = int(self.properties.get('area_radius_ft', 20))
        return battle_map.squares_in_radius(tuple(center), radius_ft, require_los=False)

    def _entities_in_area(self, battle_map, battle, center):
        entities = []
        for square in self._affected_squares(battle_map, center):
            ent = battle_map.entity_at(square[0], square[1])
            if ent is not None and ent not in entities:
                entities.append(ent)
        return entities

    def resolve(self, entity, battle, spell_action, battle_map):
        center = spell_action.target
        if isinstance(center, list):
            center = tuple(center[:2])
        targets = self._entities_in_area(battle_map, battle, center)
        dc = entity.spell_save_dc('intelligence')
        results = []
        for target in targets:
            save_roll = target.save_throw('wisdom', battle, {'is_magical': True})
            if save_roll.result() >= dc:
                results.append({
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': 'slow',
                    'spell_save': save_roll,
                    'dc': dc,
                })
            else:
                results.append({
                    'source': entity,
                    'target': target,
                    'type': 'slow',
                    'spell': self.properties,
                    'effect': self,
                    'spell_save': save_roll,
                    'dc': dc,
                })
        if not results:
            results.append({
                'type': 'spell_miss',
                'source': entity,
                'target': entity,
                'attack_name': 'slow',
                'message': 'no_targets',
            })
        return results

    @staticmethod
    def speed_override(entity, opt=None):
        opt = opt or {}
        return max(int(opt.get('value', 30)) // 2, 0)

    @staticmethod
    def ac_bonus(entity, opt=None):
        return -2

    @staticmethod
    def end_of_turn(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        battle = opt.get('battle')
        source = opt.get('source')
        if effect is None or battle is None or source is None:
            return
        dc = source.spell_save_dc('intelligence')
        save_roll = entity.save_throw('wisdom', battle, {'is_magical': True})
        if save_roll.result() >= dc:
            entity.dismiss_effect(effect)

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session if battle else item['source'].session
        if item.get('type') != 'slow':
            return None

        target = item['target']
        source = item['source']
        effect = item['effect']
        duration = session.game_time + int(effect.properties.get('duration_seconds', 60))

        source.add_casted_effect({'target': target, 'effect': effect, 'expiration': duration})
        if source.current_concentration() != effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        target.register_effect('speed_override', SlowSpell, effect=effect, source=source, duration=duration)
        target.register_effect('ac_bonus', SlowSpell, method_name='ac_bonus', effect=effect, source=source, duration=duration)
        target.register_effect('slow', SlowSpell, effect=effect, source=source, duration=duration)
        target.register_event_hook(
            'end_of_turn', SlowSpell,
            effect=effect, source=source,
        )
        if 'slowed' not in target.statuses:
            target.statuses.append('slowed')

        session.event_manager.received_event({
            'event': 'spell_debuff',
            'spell': effect,
            'source': source,
            'target': target,
        })
        return target

    def dismiss(self, entity, _descriptor=None, _opts=None):
        try:
            entity.remove_modifier(self)
        except Exception:
            pass
        if 'slowed' in getattr(entity, 'statuses', []):
            entity.statuses.remove('slowed')
