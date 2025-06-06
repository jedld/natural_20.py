import pdb
class EntityStateEvaluator:
    # Safely evaluates a DSL to return a boolean expression
    # @param conditions [String]
    # @param context [Dict]
    # @return [bool]
    def eval_if(self, conditions, context=None):
        if context is None:
            context = {}
        or_groups = conditions.split('|')
        for g in or_groups:
            and_groups = g.split('&')
            for and_g in and_groups:
                cmd, test_expression = and_g.strip().split(':')
                invert = test_expression[0] == '!'
                if test_expression[0] == '!':
                    test_expression = test_expression[1:]

                result = False
                if cmd == 'inventory':
                    result = self.item_count(test_expression) > 0
                elif cmd == 'equipped':
                    result = test_expression in [item['name'] for item in self.equipped_items()]
                elif cmd == 'object_type':
                    result = str(context.get('item_type', '')).lower() == str(test_expression).lower()
                elif cmd == 'target':
                    if test_expression == 'object':
                        result = context.get('target', '').object()
                    elif test_expression == 'elf':
                        result = context.get('target', '').race() == 'elf'
                    elif test_expression == 'human':
                        result = context.get('target', '').race() == 'human'
                    elif test_expression == 'undead':
                        result = context.get('target', '').race() == 'undead'
                    elif test_expression == 'prone':
                        result = context.get('target', '').prone()
                    elif test_expression == 'small_creature':
                        result = context.get('target', '').size() == 'small'
                    elif test_expression == 'medium_creature':
                        result = context.get('target', '').size() == 'medium'
                    elif test_expression == 'large_creature':
                        result = context.get('target', '').size() == 'large'
                    else:
                        result = False
                elif cmd == 'entity':
                    result = (test_expression == 'pc' and self.pc()) or (test_expression == 'npc' and self.npc())
                elif cmd == 'state':
                    if test_expression == 'unconscious':
                        result = self.unconscious()
                    elif test_expression == 'stable':
                        result = self.stable()
                    elif test_expression == 'dead':
                        result = self.dead()
                    elif test_expression == 'conscious':
                        result = self.conscious()
                    elif test_expression == 'prone':
                        result = self.prone()
                    elif test_expression == 'activated':
                        result = self.activated
                    elif test_expression == 'grappling':
                        result = self.is_grappling()
                else:
                    raise ValueError(f"Invalid expression {cmd} {test_expression}")

                result = not result if invert else result
                if result:
                    return True
        return False

    def apply_effect(self, expression, context=None):
        if context is None:
            context = {}
        action, value = expression.split(':')

        if action == 'status':
            return {
                'source': self,
                'type': value,
                'battle': context.get('battle'),
                'flavor': context.get('flavor'),
                'context': context
            }
        elif action == 'effect':
            return {
                'source': self,
                'effect': value,
                'type': 'effect',
                'battle': context.get('battle'),
                'flavor': context.get('flavor'),
                'context': context
            }
        return None
