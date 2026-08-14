from natural20.concern.container import Container

class Lootable(Container):
    def available_interactions(self, entity, battle=None, admin=False):
        interactions = {}
        if self.unconscious() or self.dead():
            interactions['loot'] = {}
            if self.dead() and entity is not None and entity is not self:
                from natural20.utils.portable_creature import can_pickup_creature
                ok, reason = can_pickup_creature(entity, self, battle=battle)
                if ok:
                    interactions['carry'] = {}
                else:
                    interactions['carry'] = {
                        'disabled': True,
                        'disabled_text': reason or 'Cannot carry',
                    }
        else:
            interactions['give'] = {}
        return interactions

    def build_map(self, action, action_object):
            if action == 'carry':
                return action_object
            if action == 'give':
                mode = 'give'
            else:
                mode = 'loot'

            def next_action(items):
                action_object.other_params = items
                return action_object
            return {
                'action': action_object,
                'param': [{
                    'type': 'select_items',
                    'mode': mode,
                    'label': action_object.source.items_label(),
                    'items': action_object.source.inventory
                }],
                'next': next_action
            }

    def resolve(self, entity, action, other_params, opts=None):
            if opts is None:
                opts = {}
            if action == 'carry':
                return {
                    'action': action,
                    'source': entity,
                    'target': self,
                    'battle': opts.get('battle')
                }
            if action in ['give', 'loot', 'pickup_drop']:
                return {
                    'action': action,
                    'items': other_params,
                    'source': entity,
                    'target': self,
                    'battle': opts.get('battle')
                }