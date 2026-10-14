"""Feat attack options (see ``natural20/utils/attack_options.py``).

* ``AttackOptionAction`` arms a ``timing: before_attack`` option (e.g. Precise
  Strike). It costs no action; the option applies to the next weapon attack
  roll this turn.
* ``AttackOptionHitAction`` resolves a ``timing: on_hit`` option (e.g.
  Demoralizing Strike) after a weapon hit; ``AttackOptionHitOffer`` is the
  ``on_attack_hit`` hook that offers it through ``controller.select_reaction``.
"""

from natural20.action import Action, AsyncReactionHandler
from natural20.effects.next_attack_advantage_effect import NextAttackAdvantageEffect
from natural20.utils import attack_options as ao
from natural20.utils.class_feature_registry import register_class_feature
from natural20.utils.fear import apply_fear


class AttackOptionAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.option = None

    @staticmethod
    def before_attack_options(entity):
        return [o for o in ao.attack_options_for(entity) if o.get('timing') == 'before_attack']

    @staticmethod
    def can(entity, battle):
        if battle is None:
            return False
        state = battle.entity_state_for(entity)
        if not state or (state.get('action', 0) <= 0 and not state.get('extra_attacks_remaining')):
            return False
        return any(AttackOptionAction.option_ready(entity, battle, o)
                   for o in AttackOptionAction.before_attack_options(entity))

    @staticmethod
    def option_ready(entity, battle, option):
        return ao.option_available(entity, battle, option) and ao.pending_option_effect(entity, option['id']) is None

    @staticmethod
    def build_all(session, entity, _feature_id=None, battle=None):
        actions = []
        for option in AttackOptionAction.before_attack_options(entity):
            action = AttackOptionAction(session, entity, option['id'])
            action.option = option
            actions.append(action)
        return actions

    def available(self, battle):
        return self.option is not None and self.option_ready(self.source, battle, self.option)

    def label(self):
        name = (self.option or {}).get('name') or self.action_type
        pool = ao.option_pool(self.source, self.option) if self.option else None
        return f"{name} ({pool.current})" if pool is not None else name

    def button_image(self):
        return (self.option or {}).get('icon') or 'attack_option'

    def __str__(self):
        return f"AttackOption({self.action_type})"

    __repr__ = __str__

    def build_map(self):
        if self.option is None:
            self.option = next((o for o in self.before_attack_options(self.source)
                                if o['id'] == self.action_type), None)
        return self

    def resolve(self, session, battle_map=None, opts=None):
        self.build_map()
        self.result = [{
            'type': 'attack_option_armed',
            'source': self.source,
            'option': self.option,
            'battle': (opts or {}).get('battle'),
        }] if self.option else []
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'attack_option_armed':
            return
        if session is None and battle is not None:
            session = battle.session
        ao.activate_before_attack_option(item['source'], battle, item['option'])
        if session is not None:
            session.event_manager.received_event({
                'event': 'attack_option_armed',
                'source': item['source'],
                'option': item['option'].get('name') or item['option']['id'],
            })


class AttackOptionHitAction(Action):
    def __init__(self, session, source, option, target, hit_result):
        super().__init__(session, source, option['id'])
        self.option = option
        self.target = target
        self.hit_result = hit_result or {}

    def label(self):
        pool = ao.option_pool(self.source, self.option)
        return f"{self.option.get('name') or self.option['id']} ({pool.current})"

    def button_label(self):
        return self.label()

    def name(self):
        return self.label()

    def _save_targets(self, battle):
        targets = [self.target]
        radius = (self.option.get('save') or {}).get('radius')
        if radius and battle is not None:
            battle_map = battle.map_for(self.target)
            if battle_map is not None:
                for creature in battle_map.entities_in_range(self.target, int(radius)):
                    if creature is self.source or creature in targets or creature.dead():
                        continue
                    if callable(getattr(creature, 'save_throw', None)):
                        targets.append(creature)
        return targets

    def _follow_up_candidates(self, battle):
        follow = self.option.get('follow_up_attack')
        if not follow or battle is None:
            return []
        battle_map = battle.map_for(self.target)
        weapon_key = self.hit_result.get('weapon')
        if battle_map is None or not isinstance(weapon_key, str):
            return []
        weapon = self.source.session.load_weapon(weapon_key) or {}
        reach = weapon.get('range_max') or weapon.get('range', 5)
        near = int(follow.get('range', 5))
        out = []
        for creature in battle_map.entities_in_range(self.target, near):
            if creature is self.source or creature is self.target or creature.dead():
                continue
            if creature not in battle.entities:
                continue
            if battle_map.distance(self.source, creature) * battle_map.feet_per_grid > reach:
                continue
            out.append(creature)
        return out

    def resolve(self, session, battle_map=None, opts=None):
        battle = (opts or {}).get('battle') or self.hit_result.get('battle')
        results = []
        if self.option.get('extra_damage'):
            results.append(ao.extra_damage_item(self.source, self.hit_result, self.option))
        save = self.option.get('save')
        item = {
            'type': 'attack_option_hit',
            'source': self.source,
            'target': self.target,
            'option': self.option,
            'battle': battle,
        }
        if save:
            dc = ao.option_save_dc(self.source, self.option)
            ability = ao._ABILITY_NAMES.get(save.get('ability', 'wisdom'), save.get('ability', 'wisdom'))
            fail_condition = (self.option.get('on_fail') or {}).get('condition')
            saves = []
            for creature in self._save_targets(battle):
                roll = creature.save_throw(ability, battle, {'dc': dc, 'condition': fail_condition})
                saves.append({'target': creature, 'roll': roll, 'success': roll.result() >= dc})
            item.update({'dc': dc, 'save_ability': ability, 'saves': saves,
                         'roll': saves[0]['roll'], 'success': saves[0]['success']})
        candidates = self._follow_up_candidates(battle)
        if candidates:
            item['follow_up'] = {'weapon': self.hit_result.get('weapon'), 'candidates': candidates}
        self.result = [item] + results
        return self

    @staticmethod
    def _apply_branch(source, target, option, success):
        branch = option.get('on_success' if success else 'on_fail') or {}
        rounds = int(branch.get('rounds', 1))
        seconds = ao.ROUND_SECONDS * (rounds + 1) - 1
        outcome = None
        if branch.get('condition') == 'frightened':
            if apply_fear(target, source, duration=seconds, label=option['id']):
                outcome = 'frightened'
        if branch.get('next_attack_disadvantage'):
            NextAttackAdvantageEffect.grant(target, source=source, label=f"{option['id']}_disadvantage",
                                            duration=seconds, mode='disadvantage')
            outcome = 'next_attack_disadvantage'
        return outcome

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'attack_option_hit':
            return
        if session is None and battle is not None:
            session = battle.session
        source, target, option = item['source'], item['target'], item['option']
        ao.option_pool(source, option).consume(1)
        ao.mark_used(source, battle, option)
        saves = [dict(entry) for entry in item.get('saves') or []]
        if not saves and item.get('roll') is not None:
            saves = [{'target': target, 'roll': item['roll']}]
        for entry in saves:
            if entry['target'] is target:
                entry['success'] = item.get('success')
        outcomes = []
        for entry in saves or []:
            outcome = AttackOptionHitAction._apply_branch(source, entry['target'], option, entry.get('success'))
            outcomes.append(outcome)
            if session is not None and entry['target'] is not target:
                session.event_manager.received_event({
                    'event': 'attack_option_hit',
                    'source': source,
                    'target': entry['target'],
                    'option': option.get('name') or option['id'],
                    'dc': item.get('dc'),
                    'roll': entry.get('roll'),
                    'success': entry.get('success'),
                    'outcome': outcome,
                })
        follow = item.get('follow_up')
        if follow and battle is not None:
            from natural20.actions.granted_attack_action import grant_attack
            grant_attack(battle, source, follow.get('weapon'), follow.get('candidates') or [],
                         label=option.get('name') or option['id'])
        if session is not None:
            session.event_manager.received_event({
                'event': 'attack_option_hit',
                'source': source,
                'target': target,
                'option': option.get('name') or option['id'],
                'dc': item.get('dc'),
                'roll': item.get('roll'),
                'success': item.get('success'),
                'outcome': outcomes[0] if outcomes else None,
            })


class AttackOptionHitOffer:
    """``on_attack_hit`` hook offering one ``timing: on_hit`` attack option."""

    def __init__(self, owner, option):
        self.owner = owner
        self.option = option

    def __str__(self):
        return str(self.option['id'])

    def on_attack_hit(self, entity, opts=None):
        opts = opts or {}
        if entity is not self.owner:
            return []
        hit_result = opts.get('result') or {}
        battle = hit_result.get('battle')
        target = hit_result.get('target')
        if not hit_result.get('hit?') or battle is None or target is None or target.dead():
            return []
        if not ao.is_weapon_hit(entity, hit_result) or not ao.option_available(entity, battle, self.option):
            return []
        choices = [AttackOptionHitAction(entity.session, entity, option, target, hit_result)
                   for option in [self.option] + ao.option_variants(entity, self.option)]
        offered = choices[0]
        stored = opts.get('stored_reaction')
        controller = battle.controller_for(entity)
        if stored not in (None, False):
            selected = stored
        elif controller is None:
            selected = offered
        else:
            selected = controller.select_reaction(entity, battle, battle.map_for(entity), choices, {
                'type': self.option['id'],
                'trigger': 'on_attack_hit',
                'source': entity,
                'target': target,
                'result': hit_result,
            })
        if hasattr(selected, 'send'):
            raise AsyncReactionHandler(entity, selected, opts.get('action'), 'on_attack_hit')
        if isinstance(selected, int) and not isinstance(selected, bool) and 0 <= selected < len(choices):
            selected = choices[selected]
        offered_ids = {c.option['id'] for c in choices}
        if not isinstance(selected, AttackOptionHitAction) or selected.option['id'] not in offered_ids:
            return []
        resolved = selected.resolve(entity.session, battle.map_for(entity), {'battle': battle})
        return resolved.result or []


def install_attack_option_hooks(entity):
    """Register on-hit offers for every ``timing: on_hit`` attack option, plus
    the offer for ``weapon_hit: {timing: after_hit}`` spells (Ensnaring Strike,
    Hail of Thorns) the creature has prepared."""
    from natural20.spell.extensions.weapon_hit_spell import install_weapon_hit_spell_offer
    install_weapon_hit_spell_offer(entity)
    installed = {
        hook['handler'].option['id']
        for hook in (getattr(entity, 'entity_event_hooks', None) or {}).get('on_attack_hit', [])
        if isinstance(hook.get('handler'), AttackOptionHitOffer)
    }
    for option in ao.attack_options_for(entity):
        if option.get('timing') == 'on_hit' and option['id'] not in installed:
            entity.register_event_hook('on_attack_hit', AttackOptionHitOffer(entity, option), 'on_attack_hit')


register_class_feature(
    feature_id='attack_options',
    action_class=AttackOptionAction,
    builder=lambda session, entity, feature_id: AttackOptionAction.build_all(session, entity),
)
