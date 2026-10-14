"""War Caster "Reactive Spell": cast a spell instead of an opportunity attack.

A creature with the ``opportunity_attack_spell`` benefit (feat ``benefits``
list or class YAML ``benefits``) may answer a provoked opportunity attack by
casting a prepared spell with a casting time of one action that targets only
that creature. ``PlayerCharacter.available_actions(opportunity_attack=True)``
adds these spells next to the melee attacks; controllers set the target to the
provoking creature as they do for weapon attacks.
"""

from __future__ import annotations


def _single_target(action):
    try:
        build = action.spell_action.build_map(action)
    except Exception:
        return False
    params = (build or {}).get('param') or [] if isinstance(build, dict) else []
    if len(params) != 1:
        return False
    param = params[0]
    if param.get('type') != 'select_target' or int(param.get('num', 1) or 1) != 1:
        return False
    target_types = param.get('target_types') or ['enemies']
    return 'enemies' in target_types


def reactive_spell_actions(entity, battle):
    from natural20.utils.feat_mechanics import has_benefit
    if not has_benefit(entity, 'opportunity_attack_spell'):
        return []
    if battle is not None and not entity.has_reaction(battle):
        return []
    from natural20.utils.reaction_casts import inline_spell_action
    out = []
    for slug in entity.prepared_spells():
        try:
            details = entity.session.load_spell(slug)
        except Exception:
            continue
        if not details or str(details.get('casting_time', '')).split(':')[-1] != 'action':
            continue
        if details.get('hostile') is False:
            continue
        action = inline_spell_action(entity, slug, battle)
        if action is None or not _single_target(action):
            continue
        out.append(action)
    return out
