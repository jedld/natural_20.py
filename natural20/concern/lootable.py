from natural20.concern.container import Container

class Lootable(Container):
    def available_interactions(self, entity, battle=None, admin=False):
        interactions = {}
        if self.unconscious() or self.dead():
            interactions['loot'] = {}
        else:
            interactions['give'] = {}
        return interactions

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
        if action in ['loot','give']:
            self.transfer(result.get('battle'), result.get('target'), result.get('source'), result.get('items'))


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