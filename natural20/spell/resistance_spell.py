from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell


class ResistanceSpell(Spell):
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
        res_spell = ResistanceSpell(data['session'], data['source'], data['name'], data['properties'])
        res_spell.action = data['action']
        return res_spell

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        # Resistance is a touch-range cantrip targeting one willing creature
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
                'type': 'resistance',
                'spell': self.properties,
                'effect': self
            })
        return results

    @staticmethod
    def saving_throw_override(entity, opt=None):
        if opt is None:
            opt = {}
        # Add 1d4 to the current saving throw and then consume the effect (one use)
        save_roll = opt.get('save_roll')
        if save_roll is None:
            return None
        bonus = DieRoll.roll("1d4", description='resistance', entity=entity)
        new_roll = save_roll + bonus
        # Dismiss the effect from the caster side to drop concentration and clean up everywhere
        eff = opt.get('effect')
        try:
            if eff and hasattr(eff, 'source') and eff.source:
                eff.source.dismiss_effect(eff)
        except Exception:
            # Fallback: remove directly from entity in case source is unavailable
            try:
                if eff:
                    entity.remove_effect(eff)
            except Exception:
                pass
        return new_roll

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session if battle else (item['source'].session if 'source' in item and item['source'] else None)
        if item['type'] == 'resistance':
            # Track concentration and expiration (max 1 minute)
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': session.game_time + 60
            })

            if not item['source'].current_concentration() == item['effect']:
                item['source'].concentration_on(item['effect'])

            # Apply one-time save bonus override to the target
            item['target'].register_effect('saving_throw_override', ResistanceSpell, effect=item['effect'], source=item['source'], duration=60)

            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': item['effect'],
                'source': item['source'],
                'target': item['target']
            })
            return item['target']
