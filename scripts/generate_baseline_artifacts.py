#!/usr/bin/env python3
"""
Generate baseline artifacts for route/socket parity testing.

This script imports the Flask app and captures:
1. All URL rules (routes) with methods and endpoint names
2. All SocketIO event handlers registered
3. All endpoint names for url_for resolution

Run from the project root:
    python scripts/generate_baseline_artifacts.py

Outputs:
    plans/artifacts/routes_baseline.json
    plans/artifacts/socketio_events_baseline.json
    plans/artifacts/endpoints_baseline.json
"""
import json
import os
import sys

# Ensure webapp is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'webapp'))

def generate_artifacts():
    # The app uses relative paths (LEVEL = os.getenv('TEMPLATE_DIR', "../templates"))
    # so we need to change to the webapp directory before importing.
    # Script is at scripts/generate_baseline_artifacts.py, project root is parent.
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(scripts_dir)
    webapp_dir = os.path.join(project_root, 'webapp')
    
    # Change to webapp dir since app.py uses relative path "../templates"
    original_dir = os.getcwd()
    os.chdir(webapp_dir)
    sys.path.insert(0, webapp_dir)
    sys.path.insert(0, project_root)
    
    try:
        _generate_artifacts_inner(project_root)
    finally:
        os.chdir(original_dir)


def _generate_artifacts_inner(project_root):
    import webapp.app as app_module

    app = app_module.app
    socketio = app_module.socketio

    # ── 1. Route inventory ──────────────────────────────────────────────
    routes = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: (r.rule, r.endpoint)):
        entry = {
            "rule": rule.rule,
            "endpoint": rule.endpoint,
            "methods": sorted(rule.methods),
        }
        routes.append(entry)

    routes_path = os.path.join(project_root, 'plans', 'artifacts', 'routes_baseline.json')
    os.makedirs(os.path.dirname(routes_path), exist_ok=True)
    with open(routes_path, 'w') as f:
        json.dump(routes, f, indent=2, sort_keys=True)
    print(f"Written {len(routes)} routes to {routes_path}")

    # ── 2. SocketIO event inventory ─────────────────────────────────────
    # Flask-SocketIO stores handlers internally. We extract them via the
    # python-socketio server object. Different versions expose handlers
    # differently, so we try multiple approaches.
    socketio_events = []
    try:
        # Approach 1: Try socketio.server (python-socketio Server object)
        server = getattr(socketio, '_server', None) or getattr(socketio, 'server', None)
        if server is not None:
            # python-socketio stores handlers in server.handlers[namespace][event]
            handlers_dict = getattr(server, 'handlers', None)
            if handlers_dict:
                for namespace, events in handlers_dict.items():
                    for event_name in events:
                        socketio_events.append({
                            "namespace": namespace,
                            "event": event_name,
                        })
    except Exception as e:
        print(f"Warning: Approach 1 for SocketIO events failed: {e}")

    # Approach 2: If no events found, try to inspect registered decorators
    if not socketio_events:
        try:
            # Flask-SocketIO keeps a list of decorated functions internally
            # Try to access via the internal _handlers attribute
            handlers = getattr(socketio, '_handlers', None)
            if handlers:
                for namespace, events in handlers.items():
                    for event_name in events:
                        socketio_events.append({
                            "namespace": namespace,
                            "event": event_name,
                        })
        except Exception as e:
            print(f"Warning: Approach 2 for SocketIO events failed: {e}")

    # Approach 3: Hard-coded list from @socketio.on() decorators in app.py
    # This is the fallback when dynamic extraction fails
    if not socketio_events:
        socketio_events = [
            {"namespace": "/", "event": "connect"},
            {"namespace": "/", "event": "disconnect"},
            {"namespace": "/", "event": "message"},
            {"namespace": "/", "event": "register"},
            {"namespace": "/", "event": "request_effects"},
        ]
        print("Using hardcoded SocketIO event list (fallback)")

    socketio_path = os.path.join(project_root, 'plans', 'artifacts', 'socketio_events_baseline.json')
    with open(socketio_path, 'w') as f:
        json.dump(socketio_events, f, indent=2, sort_keys=True)
    print(f"Written {len(socketio_events)} SocketIO events to {socketio_path}")

    # ── 3. Endpoint names inventory ─────────────────────────────────────
    endpoints = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.endpoint):
        endpoint = rule.endpoint
        if endpoint not in [e["endpoint"] for e in endpoints]:
            endpoints.append({
                "endpoint": endpoint,
                "rule": rule.rule,
            })

    endpoints_path = os.path.join(project_root, 'plans', 'artifacts', 'endpoints_baseline.json')
    with open(endpoints_path, 'w') as f:
        json.dump(endpoints, f, indent=2, sort_keys=True)
    print(f"Written {len(endpoints)} unique endpoints to {endpoints_path}")

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\nBaseline artifacts generated:")
    print(f"  Routes: {len(routes)}")
    print(f"  SocketIO events: {len(socketio_events)}")
    print(f"  Unique endpoints: {len(endpoints)}")

if __name__ == '__main__':
    generate_artifacts()
