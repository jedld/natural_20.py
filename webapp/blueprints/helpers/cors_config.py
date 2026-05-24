"""CORS origin resolution for Flask and SocketIO."""
import logging
import os
from fnmatch import fnmatch

logger = logging.getLogger('werkzeug')


def _is_production_env():
    is_aws = os.environ.get('AWS_ENVIRONMENT', 'false').lower() == 'true'
    is_production = os.environ.get('FLASK_ENV', 'development') == 'production'
    return is_aws or is_production


def get_allowed_origins():
    """Return allowed CORS origins from env or environment defaults."""
    cors_origins = os.environ.get('CORS_ORIGINS')
    if cors_origins:
        origins = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
        logger.info(f"Using CORS origins from environment: {origins}")
        return origins

    if _is_production_env():
        default_origins = [
            "http://natural20-alb-1402295348.us-east-1.elb.amazonaws.com",
            "https://natural20-alb-1402295348.us-east-1.elb.amazonaws.com",
            "https://0ad1d39fb719.ngrok.app",
            "https://*.ngrok-free.dev",
            "http://*.ngrok-free.dev",
            "*",
        ]
    else:
        default_origins = [
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:5001",
            "http://127.0.0.1:5001",
            "https://0ad1d39fb719.ngrok.app",
            "https://*.ngrok.io",
            "https://*.ngrok-free.app",
            "https://*.ngrok-free.dev",
            "http://*.ngrok.io",
            "http://*.ngrok-free.app",
            "http://*.ngrok-free.dev",
        ]

    logger.info(
        "Using default CORS origins for %s: %s",
        'production' if _is_production_env() else 'development',
        default_origins,
    )
    return default_origins


def origin_allowed(origin, allowed_origins):
    """Return True when ``origin`` matches an entry in ``allowed_origins``."""
    if not origin:
        return False

    normalized_origin = origin.lower()
    for allowed_origin in allowed_origins:
        candidate = str(allowed_origin).strip().lower()
        if not candidate:
            continue
        if candidate == '*':
            return True
        if candidate == normalized_origin:
            return True
        if '*' in candidate and fnmatch(normalized_origin, candidate):
            return True

    return False


def socketio_async_mode():
    """Pick SocketIO async mode based on deployment environment."""
    return 'eventlet' if _is_production_env() else 'threading'
