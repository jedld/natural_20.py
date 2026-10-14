"""Summon <spirit> spells (2024 style: Summon Fiend, Summon Beast, ...).

The caster picks a variant, then an empty square in range. The spirit is an
NPC whose stat block scales with the slot level, driven by the spell YAML::

    summon_spirit:
      base_level: 6
      ac_base: 12                 # AC = ac_base + slot level
      hp_per_slot: 15             # extra max HP per slot level above base_level
      damage_bonus_base: 3        # each attack deals damage_die + damage_bonus_base + slot level
      multiattack: half_level     # attacks per Multiattack = slot level // 2
      variants:
        demon: {npc: fiendish_spirit_demon, hp: 50, label: Demon}

Attack rolls use the caster's spell attack modifier, and any spirit-side save
DC (``save_dc: spell`` on an action / ``death_throes``) uses the caster's
spell save DC. The spirit joins the caster's side and takes its turn right
after the caster. It disappears when concentration ends or at 0 HP.
"""
from __future__ import annotations

import copy

from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell


def _config(properties):
    return dict((properties or {}).get('summon_spirit') or {})


class SummonSpiritEffect:
    def __init__(self, source, creature_uid, spell_properties):
        self.source = source
        self.creature_uid = creature_uid
        self.spell_properties = dict(spell_properties or {})

    @property
    def id(self):
        return str(self.spell_properties.get('id') or 'summon_spirit')

    def __str__(self):
        return self.id

    def label(self):
        return self.spell_properties.get('label') or self.id

    def creature(self):
        session = getattr(self.source, 'session', None)
        return session.entity_by_uid(self.creature_uid) if session is not None and self.creature_uid else None

    def dismiss(self, entity, _descriptor=None, opts=None):
        creature = self.creature()
        self.creature_uid = None
        if creature is None:
            return
        session = creature.session
        from natural20.utils.combat_comms import battle_for
        battle = battle_for(creature)
        throes = creature.properties.get('death_throes') or creature.properties.get('death_burst')
        if isinstance(throes, dict) and throes.get('on_spell_end') and not creature.dead():
            from natural20.utils.monster_traits import trigger_death_burst
            trigger_death_burst(creature, battle)
        if battle is not None and creature in getattr(battle, 'entities', {}):
            battle.remove(creature)
        try:
            battle_map = session.map_for_entity(creature)
        except Exception:
            battle_map = None
        if battle_map is not None:
            try:
                battle_map.remove(creature, battle=battle)
            except Exception:
                pass
        session.event_manager.received_event({
            'event': 'summons_dismissed', 'source': self.source, 'count': 1, 'reason': 'spell_ended',
        })


def spirit_overrides(caster, properties, variant_key, level, spell_action=None):
    """Stat overrides for the spirit's NPC template at ``level``."""
    from natural20.utils.summons import npc_template
    cfg = _config(properties)
    variant = (cfg.get('variants') or {}).get(variant_key) or {}
    base_level = int(cfg.get('base_level', properties.get('level', 1)))
    template = npc_template(caster.session, variant['npc']) or {}
    attack_bonus = caster.spell_attack_modifier_for(properties)
    save_dc = caster.spell_save_dc(HoldPersonSpell._caster_spell_ability(caster, spell_action)) \
        if spell_action is not None else 8 + caster.proficiency_bonus()
    damage_bonus = int(cfg.get('damage_bonus_base', 0)) + int(level)

    actions = []
    for action in copy.deepcopy(template.get('actions') or []):
        if action.get('type') in ('melee_attack', 'ranged_attack'):
            dice = str(action.get('damage_die') or '1d6').split('+')[0]
            action['attack'] = attack_bonus
            action['damage_die'] = f"{dice}+{damage_bonus}"
        if action.get('save_dc') == 'spell':
            action['save_dc'] = save_dc
        actions.append(action)

    hp = int(variant.get('hp', template.get('max_hp', 10))) + int(cfg.get('hp_per_slot', 0)) * max(0, level - base_level)
    overrides = {
        'default_ac': int(cfg.get('ac_base', 10)) + int(level),
        'max_hp': hp,
        'actions': actions,
        'summon_level': int(level),
        'spell_save_dc': save_dc,
    }
    if cfg.get('multiattack') == 'half_level':
        count = max(1, int(level) // 2)
        names = [a['name'] for a in actions if a.get('multiattack_group')]
        if names:
            overrides['multiattack'] = [{'any_of': names, 'count': count}]
    death_throes = template.get('death_throes')
    if isinstance(death_throes, dict):
        throes = dict(death_throes)
        throes['dc'] = save_dc
        dice = str(throes.get('damage_die') or '2d10').split('+')[0]
        throes['damage_die'] = f"{dice}+{int(level)}"
        overrides['death_throes'] = throes
    return overrides


class SummonSpiritSpell(Spell):
    def build_map(self, orig_action):
        cfg = _config(self.properties)
        variants = cfg.get('variants') or {}

        def set_point(target):
            action = orig_action.clone()
            action.target = target
            action.summon_variant = getattr(orig_action, 'summon_variant', None)
            return action

        point_param = {'param': [{'type': 'select_empty_space', 'num': 1,
                                  'range': self.properties.get('range', 90), 'require_los': True}],
                       'next': set_point}
        if getattr(orig_action, 'summon_variant', None) or len(variants) <= 1:
            if len(variants) == 1 and not getattr(orig_action, 'summon_variant', None):
                orig_action.summon_variant = next(iter(variants))
            return point_param

        def set_variant(choice):
            action = orig_action.clone()
            action.summon_variant = str(choice)
            return self.build_map(action)

        choices = [[str(v.get('label') or k).title(), k] for k, v in variants.items()]
        return {'param': [{'type': 'select_choice', 'choices': choices, 'num': 1}], 'next': set_variant}

    def resolve(self, entity, battle, spell_action, battle_map):
        cfg = _config(self.properties)
        variants = cfg.get('variants') or {}
        variant = getattr(spell_action, 'summon_variant', None) \
            or getattr(getattr(self, 'action', None), 'summon_variant', None)
        if variant not in variants:
            variant = next(iter(variants), None)
        target = spell_action.target
        if variant is None or not isinstance(target, (list, tuple)) or len(target) != 2:
            return [{'type': 'spell_miss', 'source': entity, 'target': entity, 'attack_name': str(self),
                     'message': 'no_target', 'spell': self.properties}]
        level = int(getattr(spell_action, 'at_level', None) or self.properties.get('level', 1))
        return [{
            'type': 'summon_spirit', 'source': entity, 'target': [int(target[0]), int(target[1])],
            'variant': variant, 'level': level, 'map': battle_map, 'spell': self.properties, 'effect': self,
            'overrides': spirit_overrides(entity, self.properties, variant, level, spell_action),
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'summon_spirit':
            return None
        source = item['source']
        session = session or (battle.session if battle is not None else source.session)
        spell = item.get('spell') or {}
        cfg = _config(spell)
        variant = (cfg.get('variants') or {}).get(item['variant']) or {}
        battle_map = item.get('map') or (battle.map_for(source) if battle is not None else session.map_for_entity(source))
        if battle_map is None:
            return None
        in_battle = battle is not None and source in getattr(battle, 'entities', {})
        group = battle.entities[source].get('group') if in_battle else getattr(source, 'group', 'a')

        source.remove_effect(str(spell.get('id') or 'summon_spirit'))
        name = f"{variant.get('label') or item['variant'].title()} Spirit"
        creature = session.npc(variant['npc'], {'name': name, 'group': group, 'overrides': item['overrides']})
        creature.group = group
        creature.properties['summoner_uid'] = source.entity_uid
        creature.properties['summon_name'] = spell.get('id')
        creature.properties['vanish_on_death'] = True

        x, y = item['target']
        if not battle_map.placeable(creature, x, y, battle):
            from natural20.utils.summons import _placement_squares
            spot = next((sq for sq in _placement_squares(battle_map, (x, y), 3)
                         if battle_map.placeable(creature, sq[0], sq[1], battle)), None)
            if spot is None:
                return None
            x, y = spot
        battle_map.place((x, y), creature, None, battle)
        if in_battle:
            from natural20.utils.summons import _summon_controller
            controller, fresh = _summon_controller(source, battle)
            if fresh and hasattr(controller, 'register_handlers_on'):
                try:
                    controller.register_handlers_on(creature)
                except Exception:
                    pass
            caster_init = battle.entities[source].get('initiative', 0) or 0
            battle.add(creature, group, controller=controller, add_to_initiative=True,
                       custom_initiative=lambda _b, _e: caster_init - 0.01)
        else:
            session.register_entity(creature)

        duration = int(spell.get('duration_seconds', 3600))
        effect = SummonSpiritEffect(source, creature.entity_uid, spell)
        source.add_casted_effect({'target': creature, 'effect': effect,
                                  'expiration': session.game_time + duration})
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)
        session.event_manager.received_event({
            'event': 'summons_arrived', 'source': source, 'npc_label': name, 'count': 1,
            'summoned_uids': [creature.entity_uid],
        })
        return creature
