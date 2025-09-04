from natural20.spell.spell import Spell


class BaneSpell(Spell):
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
        bane_spell = BaneSpell(data['session'], data['source'], data['name'], data['properties'])
        bane_spell.action = data['action']
        return bane_spell

    def build_map(self, orig_action):
        additional_targets = 0
        if orig_action.at_level > 1:
            additional_targets = orig_action.at_level - 1

        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 3 + additional_targets,
                    'range': self.properties['range'],
                    'unique_targets': True,
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }

    def resolve(self, entity, battle, spell_action, _battle_map):
        # Each target makes a Charisma save; on failure, bane applies.
        targets = spell_action.target
        results = []
        if not isinstance(targets, list):
            targets = [targets]

        for target in targets:
            save_roll = target.save_throw('charisma', battle)
            # Clerics use Wisdom for save DC calculation
            dc = entity.spell_save_dc('wisdom')
            if save_roll < dc:
                results.append({
                    'source': entity,
                    'target': target,
                    'type': 'bane',
                    'spell': self.properties,
                    'effect': self,
                    'spell_save': save_roll,
                    'dc': dc
                })
            else:
                results.append({
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': 'bane',
                    'attack_roll': None,
                    'advantage_mod': None,
                    'adv_info': None,
                    'spell_save': save_roll,
                    'dc': dc,
                    'cover_ac': None
                })

        return results

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session if battle else item['source'].session
        if item['type'] == 'bane':
            # Track concentration and expiration like Bless
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': session.game_time + 60
            })

            if not item['source'].current_concentration() == item['effect']:
                item['source'].concentration_on(item['effect'])

            # Register debuff effect key 'bane' on target
            item['target'].register_effect('bane', BaneSpell, effect=item['effect'], source=item['source'], duration=60)
            session.event_manager.received_event({
                'event': 'spell_buf',  # reuse generic event for client logs
                'spell': item['effect'],
                'source': item['source'],
                'target': item['target']
            })
            return item['target']
