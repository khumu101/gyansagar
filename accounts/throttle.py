"""Tiny brute-force protection for the login form (per IP + username, uses Django's cache)."""
import hashlib

from django.conf import settings
from django.core.cache import cache

from core.utils import client_ip


def _key(request, username):
    digest = hashlib.sha256(f"{client_ip(request)}|{username.strip().lower()}".encode()).hexdigest()
    return f"login-fail:{digest}"


def is_locked(request, username):
    return cache.get(_key(request, username), 0) >= settings.LOGIN_MAX_ATTEMPTS


def register_failure(request, username):
    key = _key(request, username)
    cache.add(key, 0, settings.LOGIN_LOCKOUT_MINUTES * 60)
    try:
        cache.incr(key)
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, settings.LOGIN_LOCKOUT_MINUTES * 60)


def reset(request, username):
    cache.delete(_key(request, username))


def hit(request, scope, limit, window=3600):
    """Count one request for (scope, client IP). True while the IP is still within `limit` per `window` seconds."""
    key = "rl:%s:%s" % (scope, hashlib.sha256(client_ip(request).encode()).hexdigest())
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    return count <= limit
