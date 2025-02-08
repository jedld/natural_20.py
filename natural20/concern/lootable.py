class Lootable:
    def available_interactions(self, entity, battle=None):
        if self.unconscious() or self.dead():
            return {'loot': {}}
        else:
            return { 'give': {} }

    def build_map(self, action, action_object):
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

    def use(self, entity, result, session=None):
        action = result.get('action')
        if action == 'give':
            self.transfer(result.get('battle'), result.get('target'), result.get('source'), result.get('items'))

    def is_interactable(self):
        return True

    def resolve(self, entity, action, other_params, opts=None):
            if opts is None:
                opts = {}
            if action in ['give', 'loot', 'pickup_drop']:
                return {
                    'action': action,
                    'items': other_params,
                    'source': entity,
                    'target': self,
                    'battle': opts.get('battle')
                }