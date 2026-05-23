from natural20.action import Action
from natural20.die_roll import Rollable
import pdb
import math



def to_advantage_str(item):
    if 'adv_info' not in item or item['adv_info'] is None:
        return ''
    advantage_info, disadvantage_info = item['adv_info']
    advantage_str = f' with advantage{advantage_info}' if item['advantage_mod'] > 0 else f' with disadvantage{disadvantage_info}' if item['advantage_mod'] < 0 else ''
    return advantage_str

def damage_event(item, battle):
    if battle:
        session = battle.session
    else:
        session = item['source'].session

    target = item['target']
    dmg = item['damage'].result() if isinstance(item['damage'], Rollable) else item['damage']
    dmg += item['sneak_attack'].result() if item.get('sneak_attack') is not None else 0

    session.event_manager.received_event({
        'source': item['source'],
        'attack_roll': item.get('attack_roll', None),
        'target': item['target'],
        'event': 'attacked',
        'attack_name': item['attack_name'],
        'damage_type': item['damage_type'],
        'advantage_mod': item.get('advantage_mod', None),
        'as_legendary_action': item.get('as_legendary_action', False),
        'as_reaction': item.get('as_reaction', False),
        'damage_roll': item['damage'],
        'sneak_attack': item.get('sneak_attack',False),
        'adv_info': item.get('adv_info', None),
        'thrown': item.get('thrown', False),
        'spell_save': item.get('spell_save', None),
        'dc': item.get('dc', None),
        'resistant': target.resistant_to(item['damage_type'], source=item.get('source'), weapon=item.get('weapon')),
        'vulnerable': target.vulnerable_to(item['damage_type']),
        'value': dmg
    })

    critical = item['attack_roll'].nat_20() if item.get('attack_roll') else False

    item['target'].take_damage(dmg, battle=battle, critical=critical,
                               session=session,
                               damage_type=item['damage_type'],
                               roll_info=item['damage'],
                               sneak_attack=item.get('sneak_attack', False),
                               item=item)



def after_attack_roll_hook(battle, target, source, attack_roll, effective_ac, opts=None):
    if opts is None:
        opts = {}
    force_miss = False

    # check prepared spells of target for a possible reaction
    events = []

    if attack_roll:
        results = target.resolve_trigger('after_attack_roll_target', { 'attack_roll': attack_roll } )
        if results:
            events.append(results)

    if not isinstance(target, list) and not isinstance(target, tuple):
        targets = [target]
    else:
        targets = target

    for target in targets:
        if hasattr(target, 'prepared_spells'):
            for spell in target.prepared_spells():
                spell_details = target.session.load_spell(spell)
                qty, resource = spell_details['casting_time'].split(':')

                if target.has_reaction(battle) and target.conscious() and resource == 'reaction':
                    # Only consider reaction spells whose trigger is an attack
                    # roll (e.g. Shield). Damage-triggered reactions (e.g.
                    # Hellish Rebuke) are handled by after_take_damage_hook.
                    if spell_details.get('triggers_on_damage'):
                        continue

                    spell_name = spell_details['spell_class'].replace("Natural20::", "")
                    from natural20.utils.spell_loader import load_spell_class
                    try:
                        spell_class = load_spell_class(f"{spell_name}Spell")
                    except Exception:
                        continue
                    if spell_class is None or not hasattr(spell_class, 'after_attack_roll'):
                        continue
                    result, force_miss_result = spell_class.after_attack_roll(battle, target, source, attack_roll,
                                                                            effective_ac, opts)
                    force_miss = True if force_miss_result == 'force_miss' else force_miss
                    events.append(result)

        events = [item for sublist in events for item in sublist]

    # Third-party reaction scan: spells like Silvery Barbs trigger from any
    # creature within range that can see the attacker, not just the target.
    third_party_events = _third_party_reaction_scan(
        battle, target if not isinstance(target, list) else (target[0] if target else None),
        source, attack_roll, effective_ac, opts,
    )
    events.extend(third_party_events)

    # Phase 3 reaction registry: any handler registered via
    # ``Battle.register_reaction_trigger('attack_roll', ...)`` is fired
    # here. Handlers may set ``context['force_miss'] = True`` to short-
    # circuit the attack.
    if battle is not None and getattr(battle, 'reaction_handlers', None):
        primary_target = target if not isinstance(target, list) else (target[0] if target else None)
        ctx = {
            'target': primary_target,
            'attacker': source,
            'attack_roll': attack_roll,
            'effective_ac': effective_ac,
            'opts': opts,
            'force_miss': force_miss,
        }
        registry_events = battle.fire_reaction_window('attack_roll', ctx)
        if registry_events:
            events.extend(registry_events)
        if ctx.get('force_miss'):
            force_miss = True

    return force_miss, events


def _third_party_reaction_scan(battle, target, source, attack_roll, effective_ac, opts):
    """Scan all entities on the map for reaction spells that fire on a
    successful attack made by another creature (e.g. Silvery Barbs).

    Returns a flat list of resolved event dicts.
    """
    events = []
    if battle is None or attack_roll is None or source is None:
        return events

    # Only scan when the attack has actually succeeded — third-party reactions
    # like Silvery Barbs are only triggered on a hit.
    if attack_roll.nat_1():
        return events
    if not attack_roll.nat_20() and attack_roll.result() < effective_ac:
        return events

    try:
        bmap = battle.map_for(source)
    except Exception:
        bmap = None
    if bmap is None:
        return events

    try:
        candidates = list(battle.entities.keys())
    except Exception:
        return events

    from natural20.utils.spell_loader import load_spell_class

    seen = set()
    for caster in candidates:
        if caster is None or caster is source or caster is target:
            continue
        if id(caster) in seen:
            continue
        seen.add(id(caster))
        if not hasattr(caster, 'prepared_spells'):
            continue
        if not caster.conscious() or not caster.has_reaction(battle):
            continue

        for spell in caster.prepared_spells():
            spell_details = caster.session.load_spell(spell)
            if not spell_details:
                continue
            if not spell_details.get('triggers_on_attack_success'):
                continue
            casting_time = spell_details.get('casting_time', '')
            if ':' not in casting_time:
                continue
            _, resource = casting_time.split(':')
            if resource != 'reaction':
                continue

            spell_class_name = spell_details.get('spell_class', '').replace('Natural20::', '') + 'Spell'
            try:
                spell_class = load_spell_class(spell_class_name)
            except Exception:
                continue
            if spell_class is None or not hasattr(spell_class, 'after_attack_roll'):
                continue
            try:
                result, _force = spell_class.after_attack_roll(
                    battle, caster, source, attack_roll, effective_ac, opts,
                )
            except Exception:
                continue
            if result:
                events.extend(result)
            # Stop scanning further spells for this caster — they only get
            # one reaction.
            if not caster.has_reaction(battle):
                break

    return events


def after_take_damage_hook(battle, target, attacker, damage_opts=None):
    """Trigger reaction-cost spells that fire when an entity takes damage.

    Iterates the target's prepared spells, looking for entries flagged with
    ``triggers_on_damage: true`` (e.g. Hellish Rebuke). For each such spell
    that the target can still cast, the controller is asked whether to spend
    the reaction. Returns a list of resolved event dicts (already applied via
    ``damage_event``) for inclusion in the battle log.
    """
    if damage_opts is None:
        damage_opts = {}

    events = []

    if target is None or attacker is None or attacker is target:
        return events
    if not hasattr(target, 'prepared_spells'):
        return events
    if not target.conscious():
        return events
    # Damage that originates from the spell itself must not loop back into
    # another reaction cast on the same hit.
    if damage_opts.get('source_spell') == 'hellish_rebuke':
        return events

    if battle is not None and not target.has_reaction(battle):
        return events

    session = target.session

    for spell in target.prepared_spells():
        spell_details = session.load_spell(spell)
        if spell_details is None:
            continue
        casting_time = spell_details.get('casting_time', '')
        if ':' not in casting_time:
            continue
        _, resource = casting_time.split(':')
        if resource != 'reaction':
            continue
        if not spell_details.get('triggers_on_damage'):
            continue

        # Build a SpellAction inline (mirrors the Shield reaction wiring) so
        # that resource accounting and consume() behave normally.
        from natural20.actions.spell_action import SpellAction
        from natural20.utils.spell_loader import load_spell_class

        spell_class_name = spell_details.get('spell_class', '').replace('Natural20::', '') + 'Spell'
        try:
            spell_class = load_spell_class(spell_class_name)
        except Exception:
            continue

        action = SpellAction(session, target, 'spell')
        action.spell = spell_details
        action.level = spell_details.get('level', 1)
        action.at_level = action.level
        action.spell_class = spell_class
        spell_instance = spell_class(session, target, spell_class_name, spell_details)
        spell_instance.action = action
        action.spell_action = spell_instance
        action.target = attacker

        # Pick a spell slot (warlock/innate). We only require one if the spell
        # is leveled and the caster has slots available.
        slot_owner = target.owner if target.familiar() else target
        if action.at_level > 0 and hasattr(slot_owner, 'next_spell_slot_level'):
            for spell_class_str in spell_details.get('spell_list_classes', []):
                class_key = spell_class_str.lower()
                slot_level = slot_owner.next_spell_slot_level(class_key, action.at_level)
                if slot_level is not None:
                    action.at_level = slot_level
                    action.spellcasting_class = class_key
                    break

        # Confirm the caster actually has resources for this reaction spell.
        if not SpellAction.can_cast(target, battle, spell, at_level=action.at_level):
            continue

        # Range check: target must be within the spell's range.
        distance_ft = 0
        if battle is not None:
            try:
                bmap = battle.map_for(target)
                if bmap is not None:
                    distance_ft = bmap.distance(target, attacker) * 5
            except Exception:
                distance_ft = 0
        if distance_ft > spell_details.get('range', 60):
            continue

        controller = battle.controller_for(target) if battle else None
        chosen = action  # default: cast it (no-controller / test scenarios)
        if controller is not None and hasattr(controller, 'select_reaction'):
            try:
                chosen = controller.select_reaction(
                    target,
                    battle,
                    battle.map_for(target) if battle else None,
                    [action],
                    {
                        'trigger': 'on_damage_taken',
                        'attacker': attacker,
                        'target': target,
                        'spell': spell_details,
                    },
                )
            except Exception:
                chosen = None

        if not chosen:
            continue

        results = spell_instance.resolve(target, battle, action, None)
        spell_instance.consume(battle)

        for r in results:
            if r.get('type') == 'spell_damage':
                # Mark so the recursive damage from this spell does not retrigger.
                r['source_spell'] = 'hellish_rebuke'
                damage_event(r, battle)
            events.append(r)

    # Phase 3 reaction registry: trigger 'damage_taken' window for any
    # handler registered via ``Battle.register_reaction_trigger``.
    if battle is not None and getattr(battle, 'reaction_handlers', None):
        ctx = {
            'target': target,
            'attacker': attacker,
            'damage_opts': damage_opts,
        }
        registry_events = battle.fire_reaction_window('damage_taken', ctx)
        if registry_events:
            events.extend(registry_events)

    return events
