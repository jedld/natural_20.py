"""Lightweight request/SocketIO performance instrumentation."""
import os
import threading
import time

from flask import request

from .runtime_state import register_globals


_PERF_LOCK = threading.Lock()
_PERF_STATS = {
    'routes': {},
    'socket_emits': {},
    'slow_threshold_ms': float(os.environ.get('PERF_SLOW_MS', '250')),
    'recent_slow': [],
}
_PERF_RECENT_SLOW_MAX = 50
_PERF_SKIP_PREFIXES = ('/static', '/assets', '/libs', '/favicon', '/socket.io', '/health')


def _perf_should_track(path):
    if not path:
        return False
    return not any(path.startswith(p) for p in _PERF_SKIP_PREFIXES)


def register_perf_instrumentation(app, socketio, logger):
    """Attach timing hooks to ``app`` and wrap ``socketio.emit`` for stats."""
    register_globals(perf_lock=_PERF_LOCK, perf_stats=_PERF_STATS)

    @app.before_request
    def _perf_start_timer():
        if _perf_should_track(request.path):
            try:
                request._perf_t0 = time.perf_counter()
            except Exception:
                pass

    @app.after_request
    def _perf_stop_timer(response):
        try:
            t0 = getattr(request, '_perf_t0', None)
            if t0 is None:
                return response
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            endpoint = request.endpoint or request.path
            try:
                existing = response.headers.get('Server-Timing')
                new_val = f'app;dur={elapsed_ms:.1f}'
                response.headers['Server-Timing'] = f'{existing}, {new_val}' if existing else new_val
            except Exception:
                pass

            slow = elapsed_ms >= _PERF_STATS['slow_threshold_ms']
            with _PERF_LOCK:
                bucket = _PERF_STATS['routes'].setdefault(endpoint, {
                    'count': 0, 'total_ms': 0.0, 'max_ms': 0.0, 'last_ms': 0.0, 'slow': 0,
                })
                bucket['count'] += 1
                bucket['total_ms'] += elapsed_ms
                bucket['last_ms'] = elapsed_ms
                if elapsed_ms > bucket['max_ms']:
                    bucket['max_ms'] = elapsed_ms
                if slow:
                    bucket['slow'] += 1
                    _PERF_STATS['recent_slow'].append({
                        'ts': time.time(),
                        'endpoint': endpoint,
                        'path': request.path,
                        'method': request.method,
                        'ms': round(elapsed_ms, 1),
                        'status': response.status_code,
                    })
                    if len(_PERF_STATS['recent_slow']) > _PERF_RECENT_SLOW_MAX:
                        del _PERF_STATS['recent_slow'][
                            0:len(_PERF_STATS['recent_slow']) - _PERF_RECENT_SLOW_MAX
                        ]
            if slow:
                try:
                    logger.warning(
                        f"[perf] slow {request.method} {request.path} -> {elapsed_ms:.1f}ms "
                        f"(status {response.status_code})"
                    )
                except Exception:
                    pass
        except Exception:
            pass
        return response

    try:
        _orig_socketio_emit = socketio.emit

        def _perf_socketio_emit(event, *args, **kwargs):
            try:
                with _PERF_LOCK:
                    _PERF_STATS['socket_emits'][event] = _PERF_STATS['socket_emits'].get(event, 0) + 1
            except Exception:
                pass
            return _orig_socketio_emit(event, *args, **kwargs)

        socketio.emit = _perf_socketio_emit
    except Exception:
        pass
