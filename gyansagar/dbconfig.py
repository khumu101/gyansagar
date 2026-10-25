"""Turn DATABASE_URL (e.g. postgres://user:pass@host:5432/dbname?sslmode=require) into a Django DATABASES entry."""
from urllib.parse import parse_qsl, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

POSTGRES_SCHEMES = {"postgres", "postgresql", "pgsql"}
ALLOWED_PG_OPTIONS = {"sslmode", "sslrootcert", "connect_timeout", "application_name"}


def database_from_url(url, base_dir, conn_max_age=60):
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in ("sqlite", "sqlite3"):
        rel = unquote(parsed.path)[1:] or "db.sqlite3"  # sqlite:///db.sqlite3  |  sqlite:////abs/path.db
        name = rel if rel.startswith("/") else str(base_dir / rel)
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name}
    if scheme in POSTGRES_SCHEMES:
        name = unquote(parsed.path)[1:]
        if not name:
            raise ImproperlyConfigured("DATABASE_URL has no database name (…/dbname).")
        options = {k: v for k, v in parse_qsl(parsed.query) if k in ALLOWED_PG_OPTIONS}
        config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": name,
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
            "CONN_MAX_AGE": conn_max_age,
            "CONN_HEALTH_CHECKS": True,
        }
        if options:
            config["OPTIONS"] = options
        return config
    raise ImproperlyConfigured(f"Unsupported DATABASE_URL scheme '{scheme}'. Use postgres://… or sqlite:///…")
