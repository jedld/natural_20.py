"""Druid - Wild Shape (D&D 5e SRD 2014, levels 1-2 only).

WildShapeAction       - bonus action; consumes one wild shape charge and
                        transforms the druid into a chosen beast.
RevertWildShapeAction - bonus action; reverts the druid to humanoid form.
WildShapeAttackAction - AttackAction subclass used while transformed so
                        beast statblock attacks resolve against PC source.
"""

from natural20.action import Action
from natural20.actions.attack_action import AttackAction
from natural20.entity_class import wild_shape as ws


class WildShapeAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None  # beast id (string)
        self.as_bonus_action = True

    def label(self):
        return 'Wild Shape'

    def __repr__(self):
        return 'WildShape'

    @staticmethod
    def can(entity, battle, options=None):
        if not getattr(entity, 'class_feature', None):
            return False
        if not entity.class_feature('wild_shape'):
            return False
        if ws.is_wild_shaped(entity):
            return False
        if not getattr(entity, 'has_wild_shape', None):
            return False
        if not entity.has_wild_shape(1):
            return False
        if battle is None:
            return True
        return entity.total_bonus_actions(battle) > 0

    def build_map(self):
        def set_form(beast_id):
            self.target = beast_id
            return self

        beasts = list(ws.available_beasts(getattr(self.source, 'druid_level', None)))
        choices = []
        for beast_id in beasts:
            try:
                props = ws._load_beast_yaml(self.source.session, beast_id)
                label = props.get('label') or props.get('name') or beast_id.replace('_', ' ').title()
                cr = props.get('cr')
                cr_str = ''
                if cr is not None:
                    if cr == 0.125:
                        cr_str = ' (CR 1/8)'
                    elif cr == 0.25:
                        cr_str = ' (CR 1/4)'
                    elif cr == 0.5:
                        cr_str = ' (CR 1/2)'
                    elif cr == 0:
                        cr_str = ' (CR 0)'
                    else:
                        cr_str = f' (CR {cr})'
                display = f"{label}{cr_str}"
            except Exception:
                display = beast_id.replace('_', ' ').title()
            choices.append([display, beast_id])
        return {
            'action': self,
            'param': [
                {
                    'type': 'select_choice',
                    'choices': choices,
                    'num': 1,
                }
            ],
            'next': set_form,
        }

    def resolve(self, _session, _map, opts=None):
        opts = opts or {}
        if not self.target and ws.available_beasts(
                getattr(self.source, 'druid_level', None)):
            # Default to the first legal form when none was specified.
            self.target = ws.available_beasts(
                getattr(self.source, 'druid_level', None))[0]
        self.result = [{
            'type': 'wild_shape',
            'source': self.source,
            'form': self.target,
            'battle': opts.get('battle'),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'wild_shape':
            return
        druid = item['source']
        form = item.get('form')
        if not form:
            return
        if hasattr(druid, 'consume_wild_shape'):
            druid.consume_wild_shape(1)
        ws.transform(druid, form)
        if battle:
            battle.consume(druid, 'bonus_action')
        if session is None:
            session = battle.session if battle else getattr(druid, 'session', None)
        if session:
            session.event_manager.received_event({
                'source': druid,
                'event': 'wild_shape',
                'form': form,
            })


class RevertWildShapeAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    def label(self):
        return 'Revert Wild Shape'

    def __repr__(self):
        return 'RevertWildShape'

    @staticmethod
    def can(entity, battle, options=None):
        if not ws.is_wild_shaped(entity):
            return False
        if battle is None:
            return True
        return entity.total_bonus_actions(battle) > 0

    def build_map(self):
        return self

    def resolve(self, _session, _map, opts=None):
        opts = opts or {}
        self.result = [{
            'type': 'wild_shape_revert',
            'source': self.source,
            'battle': opts.get('battle'),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'wild_shape_revert':
            return
        druid = item['source']
        ws.revert(druid, overflow_damage=0, battle=battle)
        if battle:
            battle.consume(druid, 'bonus_action')
        if session is None:
            session = battle.session if battle else getattr(druid, 'session', None)
        if session:
            session.event_manager.received_event({
                'source': druid,
                'event': 'wild_shape_revert',
            })


class WildShapeAttackAction(AttackAction):
    """Attack used by a wild-shaped druid; treats ``npc_action`` as the weapon
    regardless of whether the source reports ``npc()`` True."""

    def clone(self):
        action = WildShapeAttackAction(self.session, self.source,
                                        self.action_type, self.opts)
        action.target = self.target
        action.using = self.using
        action.npc_action = self.npc_action
        action.as_reaction = self.as_reaction
        action.thrown = self.thrown
        action.advantage_mod = self.advantage_mod
        action.attack_roll = self.attack_roll
        return action

    def get_attack_info(self, opts=None):
        opts = opts or {}
        npc_action = opts.get('npc_action') or self.npc_action
        if npc_action is None:
            return super().get_attack_info(opts)
        return npc_action

    def get_weapon_info(self, opts):
        opts = opts or {}
        npc_action = opts.get('npc_action') or self.npc_action
        if npc_action is None:
            return super().get_weapon_info(opts)
        attack_name = npc_action.get('name')
        attack_mod = npc_action.get('attack', 0)
        damage_roll = npc_action.get('damage_die')
        ammo_type = npc_action.get('ammo')
        return npc_action, attack_name, attack_mod, damage_roll, ammo_type
