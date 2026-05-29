"""YAML-driven combat round scripts (flee countdown, delayed morphs, etc.)."""


def _emit_narration(session, entity, text, title=None):
    if not text or session is None:
        return
    try:
        session.event_manager.received_event({
            'event': 'narration',
            'source': entity,
            'narration': {
                'on_enter': {
                    'title': title or '',
                    'text': text,
                    'once': False,
                },
            },
        })
    except Exception:
        pass


def _emit_message(session, entity, message):
    if not message:
        return
    try:
        session.event_manager.received_event({
            'event': 'message',
            'source': entity,
            'message': message,
        })
    except Exception:
        pass


def _should_start_flee(entity, flee_cfg):
    if entity.properties.get('_flee_countdown_started'):
        return True
    require = flee_cfg.get('require_flag')
    if require and not entity.properties.get(require):
        return False
    auto_hp = flee_cfg.get('auto_start_hp_percent')
    if auto_hp is not None:
        try:
            max_hp = entity.max_hp()
            if max_hp and entity.hp() <= max_hp * float(auto_hp):
                entity.properties['_flee_countdown_started'] = True
                return True
        except Exception:
            pass
    if flee_cfg.get('start_immediately'):
        entity.properties['_flee_countdown_started'] = True
        return True
    return bool(entity.properties.get('_flee_countdown_started'))


def _run_on_complete(entity, battle, on_complete):
    if not on_complete:
        return False
    session = battle.session if battle else entity.session

    narration = on_complete.get('narration')
    if narration:
        _emit_narration(session, entity, narration, on_complete.get('title'))

    message = on_complete.get('message')
    if message:
        _emit_message(session, entity, message)

    phase = on_complete.get('phase_transition')
    if phase:
        if isinstance(phase, str):
            entity.properties['phase_transition'] = phase
        else:
            entity.properties['phase_transition'] = dict(phase)
        if entity._maybe_phase_transition(battle=battle):
            return True

    spawn = on_complete.get('spawn_npc')
    if spawn and session:
        try:
            from natural20.npc import Npc
            target_map = session.map_for(entity)
            if spawn.get('map'):
                target_map = session.maps.get(spawn['map']) or target_map
            if target_map is None:
                return False
            pos = spawn.get('pos')
            if pos is None and spawn.get('locate_object_type'):
                locate_type = spawn['locate_object_type']
                for obj, obj_pos in getattr(target_map, 'interactable_objects', {}).items():
                    obj_type = getattr(obj, 'type', None) or obj.properties.get('type')
                    if obj_type == locate_type:
                        pos = list(obj_pos)
                        break
            if pos is None:
                pos = list(target_map.position_of(entity) or (0, 0))
            npc_type = spawn.get('npc') or spawn.get('npc_type')
            overrides = dict(spawn.get('overrides') or {})
            new_ent = Npc(session, npc_type, {
                'name': spawn.get('name', npc_type),
                'overrides': overrides,
                'rand_life': spawn.get('rand_life', True),
            })
            group = spawn.get('group', 'b')
            target_map.add(new_ent, int(pos[0]), int(pos[1]), group=group)
            if battle is not None:
                battle.add(new_ent, map=target_map, add_to_initiative=True, group=group)
            return True
        except Exception:
            return False
    return False


def process_combat_script(entity, battle):
    """Called from Entity.reset_turn after start_of_turn hooks."""
    if battle is None or entity is None:
        return
    cfg = entity.properties.get('combat_script')
    if not cfg:
        return

    flee_cfg = cfg.get('flee_countdown')
    if flee_cfg and _should_start_flee(entity, flee_cfg):
        remaining = entity.properties.get('_flee_countdown_remaining')
        if remaining is None:
            remaining = int(flee_cfg.get('rounds', 3))
        tick = flee_cfg.get('tick_message')
        if tick:
            _emit_message(entity.session, entity, tick.format(remaining=remaining))

        remaining -= 1
        if remaining > 0:
            entity.properties['_flee_countdown_remaining'] = remaining
            return

        entity.properties['_flee_countdown_remaining'] = 0
        entity.properties['_flee_countdown_complete'] = True
        _run_on_complete(entity, battle, flee_cfg.get('on_complete') or {})
