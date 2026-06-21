from natural20.item_library.object import Object
from natural20.actions.spell_action import SpellAction
from natural20.utils.spell_loader import load_spell_class
from natural20.utils.string_utils import classify


class MagicSpellItem(Object):
    """Usable charged item that casts one or more configured spells."""

    def consumable(self):
        return bool(self.properties.get('consumable', False))

    def _resource_name(self):
        return f"{self.properties.get('name')}_charges"

    def _spell_options(self):
        if self.properties.get('spell_options'):
            return self.properties['spell_options']
        return [{'spell': self.properties['spell'], 'level': self.properties.get('level', 1), 'charges': 1}]

    def can_use(self, entity, battle):
        charges = self.properties.get('charges')
        if charges:
            resource = entity.get_resource(self._resource_name()) if hasattr(entity, 'get_resource') else None
            if resource is None:
                resource = entity.register_resource(self._resource_name(), charges, restore_on='long_rest')
            if resource.current <= 0:
                return False
        return True

    def build_map(self, action):
        options = self._spell_options()
        if len(options) > 1:
            choices = [[opt.get('label') or opt['spell'].replace('_', ' ').title(), opt['spell']] for opt in options]

            def choose_spell(choice):
                action.item_spell_choice = choice
                return self._build_spell_map(action, choice)

            return {'param': [{'type': 'select_choice', 'choices': choices, 'num': 1}], 'next': choose_spell}
        return self._build_spell_map(action, options[0]['spell'])

    def _build_spell_map(self, action, spell_name):
        option = next((opt for opt in self._spell_options() if opt['spell'] == spell_name), None)
        spell = action.session.load_spell(spell_name)
        spell_name_for_class = spell.get("spell_class", classify(spell_name)) + "Spell"
        spell_name_for_class = spell_name_for_class.replace("Natural20::", "")
        spell_class = load_spell_class(spell_name_for_class)
        action.spell_class = spell_class
        action.spell_action = spell_class(action.session, action.source, spell_name_for_class, spell)
        action.spell_action.action = action
        action.at_level = option.get('level', spell.get('level', 1)) if option else spell.get('level', 1)
        action.item_spell_choice = spell_name
        return action.spell_action.build_map(action)

    def resolve(self, entity, battle, action, battle_map):
        result = action.spell_action.resolve(entity, battle, action, battle_map)
        result.append({
            'source': entity,
            'type': 'use_item',
            'spell_action': action.spell_action,
            'item': self,
            'item_spell_choice': getattr(action, 'item_spell_choice', None),
        })
        return result

    def use(self, entity, result, session=None):
        charges = self.properties.get('charges')
        if charges:
            resource = entity.get_resource(self._resource_name())
            if resource is None:
                resource = entity.register_resource(self._resource_name(), charges, restore_on='long_rest')
            option = next((opt for opt in self._spell_options()
                           if opt['spell'] == result.get('item_spell_choice')), None)
            resource.consume((option or {}).get('charges', 1))


class PotionEffectItem(Object):
    def consumable(self):
        return True

    def can_use(self, entity, battle):
        return True

    def build_map(self, action):
        def set_target(target):
            action.target = target
            return action
        return {'param': [{'type': 'select_target', 'num': 1, 'range': 5,
                           'target_types': ['allies', 'self']}],
                'next': set_target}

    def resolve(self, entity, battle, action, _battle_map):
        return {'effect_name': self.properties.get('effect'), 'duration': self.properties.get('duration_seconds')}

    def use(self, entity, result, session=None):
        target = result.get('target') or entity
        effect = result.get('effect_name')
        if effect == 'greater_healing':
            from natural20.die_roll import DieRoll
            roll = DieRoll.roll('4d4+4', entity=entity, battle=result.get('battle'),
                                description='Potion of Greater Healing')
            target.heal(roll.result())
        elif effect:
            if effect not in target.statuses:
                target.statuses.append(effect)
            target.register_effect(effect, self.__class__, effect=self, source=entity,
                                   duration=result.get('duration'))
