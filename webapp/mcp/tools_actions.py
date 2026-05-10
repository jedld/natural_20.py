"""Action / battle-flow MCP tools.

These tools mirror the operations a DM (or the active player) would
trigger from the webapp UI: list available actions for an entity,
execute a generic action by name (uses :func:`autobuild` to materialise
target / option choices), drive movement along a path, and
start / end / advance battles.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from natural20.actions.interact_action import InteractAction
from natural20.dm import DungeonMaster

from .context import MCPContext
from .tool_registry import ToolRegistry, tool, tool_error


def _with_dm_mcp_privileges(entity: Any, fn: Callable[[], Any]) -> Any:
    """Temporarily set ``is_admin`` so interactions match DM / backstage checks."""
    old = getattr(entity, 'is_admin', False)
    try:
        entity.is_admin = True
        return fn()
    finally:
        entity.is_admin = old


def _infer_action_type_from_opts(opts: Dict[str, Any]) -> Optional[str]:
    """When models omit ``action_type`` they often put ``open`` / ``use`` in ``opts``."""
    hint = opts.get('object_action') or opts.get('action')
    if not isinstance(hint, str) or not hint.strip():
        return None
    low = hint.strip().lower()
    if low in (
        'open', 'close', 'interact', 'use', 'pick', 'lock', 'unlock',
        'pull', 'push', 'read', 'search',
    ):
        return 'InteractAction'
    return None


def _is_dm_direct_interact_context(entity_uid: Optional[str]) -> bool:
    """When True, DM interacts as DM UI does — no PC uid needed as map anchor."""
    if entity_uid is None:
        return True
    s = str(entity_uid).strip().lower()
    if not s:
        return True
    return s in (DungeonMaster.DM_ENTITY_UID.lower(), 'dm')


def register(registry: ToolRegistry) -> None:
    @tool(
        registry,
        name='actions.list_available',
        description='List the actions an entity can take right now (resource-aware). '
                    'Optional `interact_only=True` to filter to interaction actions. '
                    'Defaults `admin_actions=true` (MCP is DM-facing).',
        input_schema={
            'type': 'object',
            'required': ['entity_uid'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'interact_only': {'type': 'boolean', 'default': False},
                'admin_actions': {'type': 'boolean', 'default': True},
            },
        },
        category='actions',
    )
    def list_available(context: MCPContext, entity_uid: str,
                       interact_only: bool = False,
                       admin_actions: bool = True):
        ent = _resolve(context, entity_uid)
        battle = _safe(lambda: context.current_game.get_current_battle())
        battle_map = context.map_for_entity(ent)
        try:
            actions = _with_dm_mcp_privileges(ent, lambda: ent.available_actions(
                context.game_session, battle, auto_target=False,
                map=battle_map, interact_only=bool(interact_only),
                admin_actions=bool(admin_actions),
            )) or []
        except Exception as exc:
            raise tool_error(f'Failed to list actions: {exc}')
        rows: List[Dict[str, Any]] = []
        for act in actions:
            rows.append({
                'action_type': act.__class__.__name__,
                'name': getattr(act, 'name', None),
                'label': _safe(lambda a=act: a.label()),
                'as_action': _safe(lambda a=act: a.as_action),
                'as_bonus_action': _safe(lambda a=act: a.as_bonus_action),
            })
        return {'entity_uid': entity_uid, 'actions': rows}

    @tool(
        registry,
        name='actions.execute',
        description='Execute a non-movement action for an entity. Engine performs '
                    'auto-targeting via autobuild. Pass a target entity uid in `target` '
                    'and free-form options in `opts` (e.g. spell name, at_level). '
                    'For doors and map objects, use action_type "InteractAction" (or omit '
                    'it and set opts.action to "open", "close", etc.). '
                    'InteractAction with `target` uses the DungeonMaster actor (same as '
                    'the DM UI). Omit `entity_uid` or pass "dungeon_master" so the DM '
                    'acts directly; only pass a character uid if you need that token as '
                    'the map anchor.',
        input_schema={
            'type': 'object',
            'properties': {
                'entity_uid': {
                    'type': 'string',
                    'description': 'Required for most actions. For InteractAction with '
                                    '`target` (doors/objects), omit or use '
                                    '"dungeon_master" for DM-direct interaction.',
                },
                'action_type': {'type': 'string',
                                 'description': 'Python action class name, e.g. '
                                                '"InteractAction", "AttackAction", '
                                                '"SpellAction". Optional if opts.action '
                                                'implies an interaction.'},
                'target': {'type': 'string',
                            'description': 'Target entity or map-object uid (optional)'},
                'opts': {'type': 'object', 'default': {}},
            },
        },
        category='actions',
    )
    def execute(context: MCPContext, entity_uid: Optional[str] = None,
                action_type: Optional[str] = None,
                target: Optional[str] = None, opts: Optional[Dict[str, Any]] = None):
        opts = dict(opts or {})
        if not (action_type and str(action_type).strip()):
            inferred = _infer_action_type_from_opts(opts)
            if inferred:
                action_type = inferred
        if not action_type or not str(action_type).strip():
            raise tool_error(
                "Missing action_type for tool 'actions.execute' "
                '(or provide opts.action / opts.object_action, e.g. "open").'
            )
        action_type = str(action_type).strip()
        klass = context.resolve_action_class(action_type)
        if klass is None:
            raise tool_error(f'Unknown action type: {action_type}')

        # Mirror Flask ``select_object`` when DM acts on a map object: use
        # :class:`DungeonMaster` as ``InteractAction.source`` so doors/open work
        # without adjacency to a PC. POV/map anchor uses the target object when
        # ``entity_uid`` is omitted or ``dungeon_master`` so models need not name a PC.
        if klass.__name__ == 'InteractAction' and target is not None:
            target_obj = context.resolve_entity(target)
            if target_obj is None:
                raise tool_error(f'Target not found: {target}')
            verb = opts.get('object_action') or opts.get('action')
            if not isinstance(verb, str) or not verb.strip():
                raise tool_error(
                    'InteractAction with target requires opts.action or '
                    'opts.object_action (e.g. "open").'
                )
            verb = verb.strip()
            if _is_dm_direct_interact_context(entity_uid):
                pov_anchor = target_obj
                dm_direct = True
            else:
                pov_anchor = _resolve(context, str(entity_uid).strip())
                dm_direct = False
            gm = DungeonMaster(context.game_session, name='dm')
            interact = InteractAction(context.game_session, gm, 'interact')
            interact.object_action = verb
            interact.target = target_obj
            try:
                context.current_game.commit_and_update('dm', interact, [pov_anchor])
            except Exception as exc:
                raise tool_error(f'Action failed during commit: {exc}')
            if dm_direct:
                context.log_dm(f'DM InteractAction ({verb}) on {target_obj}')
            else:
                context.log_dm(
                    f'DM InteractAction ({verb}) on {target_obj} '
                    f'(map anchor: {pov_anchor.label()})'
                )
            context.emit_refresh()
            out: Dict[str, Any] = {
                'action_type': action_type,
                'committed': True,
                'actor': 'dungeon_master',
                'target_uid': str(getattr(target_obj, 'entity_uid', '') or ''),
            }
            if not dm_direct:
                out['context_entity_uid'] = str(getattr(pov_anchor, 'entity_uid', '') or '')
            return out

        if entity_uid is None or not str(entity_uid).strip():
            raise tool_error(
                "Missing entity_uid for tool 'actions.execute' "
                '(required for this action type).'
            )
        ent = _resolve(context, str(entity_uid).strip())
        battle = _safe(lambda: context.current_game.get_current_battle())
        battle_map = context.map_for_entity(ent)

        match: List[Any] = []
        if target is not None:
            target_entity = context.resolve_entity(target)
            if target_entity is None:
                raise tool_error(f'Target entity not found: {target}')
            match.append(target_entity)

        if klass.__name__ == 'InteractAction':
            verb = opts.get('object_action') or opts.get('action')
            if isinstance(verb, str) and verb.strip():
                match.append(verb.strip())

        from natural20.utils.action_builder import autobuild

        def _build_action():
            return autobuild(context.game_session, klass, ent, battle,
                             map=battle_map, auto_target=True,
                             match=match if match else None,
                             **opts)

        try:
            built = _with_dm_mcp_privileges(ent, _build_action)
        except Exception as exc:
            raise tool_error(f'Failed to build action: {exc}')
        if not built:
            raise tool_error('No valid action could be built (no legal targets/options)')
        action = built[0]
        try:
            _with_dm_mcp_privileges(ent, lambda: context.current_game.commit_and_update('dm', action, [ent]))
        except Exception as exc:
            raise tool_error(f'Action failed during commit: {exc}')
        context.log_dm(f"DM executed {action_type} for {ent.label()}")
        context.emit_refresh()
        return {
            'entity_uid': entity_uid,
            'action_type': action_type,
            'committed': True,
            'hp_after': _safe(lambda: ent.hp()),
        }

    @tool(
        registry,
        name='actions.move',
        description='Move an entity along a path of grid coordinates. The first '
                    'coordinate must be the entity\'s current position. In battle, '
                    'movement is enforced against the entity\'s remaining speed.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'path'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'path': {
                    'type': 'array',
                    'items': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 2, 'maxItems': 2},
                },
            },
        },
        category='actions',
    )
    def move(context: MCPContext, entity_uid: str, path: List[List[int]]):
        ent = _resolve(context, entity_uid)
        battle = _safe(lambda: context.current_game.get_current_battle())
        battle_map = context.map_for_entity(ent)
        if battle_map is None:
            raise tool_error('Entity is not on a map')
        if not path or not isinstance(path, list):
            raise tool_error('path must be a non-empty list of [x,y] pairs')
        clean: List[List[int]] = [[int(p[0]), int(p[1])] for p in path]

        from natural20.actions.move_action import MoveAction
        action = MoveAction(context.game_session, ent, 'move')
        action.move_path = clean
        try:
            context.current_game.commit_and_update('dm', action, [ent])
        except Exception as exc:
            raise tool_error(f'Move failed: {exc}')
        context.emit_refresh()
        return {
            'entity_uid': entity_uid,
            'from': clean[0],
            'to': clean[-1],
        }

    @tool(
        registry,
        name='actions.end_turn',
        description='End the current entity\'s turn (advance battle to the next combatant).',
        input_schema={'type': 'object', 'properties': {}},
        category='actions',
    )
    def end_turn(context: MCPContext):
        battle = _safe(lambda: context.current_game.get_current_battle())
        if battle is None:
            raise tool_error('No active battle')
        before = _safe(lambda: battle.current_turn().entity_uid)
        try:
            battle.next_turn()
        except Exception as exc:
            raise tool_error(f'next_turn failed: {exc}')
        after = _safe(lambda: battle.current_turn().entity_uid)
        context.emit_refresh()
        return {'previous_uid': before, 'current_uid': after,
                'round': getattr(battle, 'round', None)}

    @tool(
        registry,
        name='actions.start_battle',
        description='Start a new battle. If `combatant_uids` is given, those entities '
                    'are added (group "a"/"b" alternating) before initiative is rolled. '
                    'Otherwise this initiates with all entities currently on the active map.',
        input_schema={
            'type': 'object',
            'properties': {
                'combatant_uids': {'type': 'array', 'items': {'type': 'string'}},
                'map_name': {'type': 'string'},
            },
        },
        category='actions',
    )
    def start_battle(context: MCPContext,
                      combatant_uids: Optional[List[str]] = None,
                      map_name: Optional[str] = None):
        cg = context.current_game
        if _safe(lambda: cg.get_current_battle()) is not None:
            raise tool_error('A battle is already active; end it first.')
        battle_map = context.resolve_map(map_name)
        try:
            from natural20.battle import Battle
            battle = Battle(context.game_session, battle_map)
        except Exception as exc:
            raise tool_error(f'Failed to instantiate Battle: {exc}')

        added = 0
        if combatant_uids:
            for i, uid in enumerate(combatant_uids):
                ent = context.resolve_entity(uid)
                if ent is None:
                    raise tool_error(f'Combatant not found: {uid}')
                battle.add(ent, 'a' if i % 2 == 0 else 'b')
                added += 1
        else:
            for ent in (getattr(battle_map, 'entities', {}) or {}).keys():
                battle.add(ent, 'a' if bool(getattr(ent, 'is_npc', lambda: False)()) else 'b')
                added += 1

        try:
            battle.start()
            cg.battles[battle_map.name] = battle  # best-effort registration
        except Exception:
            pass
        # Different GameManagement variants expose different setters. Try both.
        for setter in ('set_current_battle', 'register_battle'):
            fn = getattr(cg, setter, None)
            if callable(fn):
                try:
                    fn(battle)
                    break
                except Exception:
                    continue
        context.log_dm(f"DM started battle on {getattr(battle_map, 'name', '?')} ({added} combatants)")
        context.emit_refresh()
        return {
            'started': True,
            'map': getattr(battle_map, 'name', None),
            'combatants': added,
            'round': getattr(battle, 'round', 0),
        }

    @tool(
        registry,
        name='actions.end_battle',
        description='End the current battle.',
        input_schema={'type': 'object', 'properties': {}},
        category='actions',
    )
    def end_battle(context: MCPContext):
        cg = context.current_game
        if _safe(lambda: cg.get_current_battle()) is None:
            raise tool_error('No active battle')
        try:
            cg.end_current_battle()
        except Exception as exc:
            raise tool_error(f'end_current_battle failed: {exc}')
        context.log_dm("DM ended the active battle")
        context.emit_refresh()
        return {'ended': True}


def _resolve(context: MCPContext, entity_uid: str):
    ent = context.resolve_entity(entity_uid)
    if ent is None:
        raise tool_error(f'Entity not found: {entity_uid}')
    return ent


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None
