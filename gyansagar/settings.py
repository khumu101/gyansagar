import logging
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .dbconfig import database_from_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Core / security
#   Local development works with zero setup (DEBUG on).
#   For a real server set:  DJANGO_DEBUG=0  DJANGO_SECRET_KEY=<long random>  DJANGO_ALLOWED_HOSTS=yourdomain.com
# ---------------------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set the DJANGO_SECRET_KEY environment variable when DJANGO_DEBUG=0.")
    SECRET_KEY = "dev-only-change-me-in-production"

APP_VERSION = os.environ.get("APP_VERSION", "dev")  # shown on /healthz/ and sent to Sentry as the release

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "*" if DEBUG else "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "accounts",
    "portal",
    "learning",
]

ADMIN_URL = os.environ.get("ADMIN_URL", "admin/").strip("/") + "/"  # e.g. ADMIN_URL=my-secret-panel/

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

try:  # WhiteNoise serves the collected static files in production (pip install whitenoise)
    import whitenoise  # noqa: F401
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    HAS_WHITENOISE = True
except ImportError:
    HAS_WHITENOISE = False

ROOT_URLCONF = "gyansagar.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "gyansagar.wsgi.application"

# Local dev: SQLite file, no setup. Production: set DATABASE_URL=postgres://user:pass@host:5432/dbname
if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": database_from_url(os.environ["DATABASE_URL"], BASE_DIR,
                                              conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", 60)))}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

# Shared cache (login lock, rate limits). Production: REDIS_URL=redis://redis:6379/1  (needs the `redis` package)
if os.environ.get("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                          "LOCATION": os.environ["REDIS_URL"], "KEY_PREFIX": "gyansagar"}}
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Real client IP for rate limits. Behind nginx set CLIENT_IP_HEADER=X-Client-IP (nginx.conf overwrites it).
CLIENT_IP_HEADER = os.environ.get("CLIENT_IP_HEADER", "REMOTE_ADDR")

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
# Simple rule on purpose: just a minimum length (no "too common / too similar / numbers only" checks).
# Change PASSWORD_MIN_LENGTH to make it stricter.
PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", 6))
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": PASSWORD_MIN_LENGTH}},
]

# Login with username OR e-mail
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailOrUsernameBackend"]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

SIGNUP_AUTO_LOGIN = env_bool("SIGNUP_AUTO_LOGIN", True)  # False -> send people to the login page after signup
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", 5))  # failed tries per IP+username ...
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", 15))  # ... before a temporary lock
EMAIL_VERIFY_MAX_AGE_HOURS = int(os.environ.get("EMAIL_VERIFY_MAX_AGE_HOURS", 72))
# True -> community posting + AI Tutor need a verified e-mail (turn on once SMTP works). Downloads stay open to everyone.
REQUIRE_VERIFIED_EMAIL = env_bool("REQUIRE_VERIFIED_EMAIL", False)
REPORT_AUTOHIDE_THRESHOLD = int(os.environ.get("REPORT_AUTOHIDE_THRESHOLD", 3))  # open reports from different people -> hidden
# "Continue with Google" (see accounts/google.py). Leave empty to hide the button.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")  # default: built from the request, e.g. https://domain/accounts/google/callback/
SIGNUP_MAX_PER_HOUR = int(os.environ.get("SIGNUP_MAX_PER_HOUR", 20))  # new accounts per IP per hour
PASSWORD_RESET_MAX_PER_HOUR = int(os.environ.get("PASSWORD_RESET_MAX_PER_HOUR", 10))  # reset requests per IP per hour

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # "Keep me logged in" lasts 14 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------------------
# E-mail (password reset). Prints e-mails in the terminal unless EMAIL_HOST is set.
# ---------------------------------------------------------------------------
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Gyansagar <no-reply@gyansagar.local>")

# ---------------------------------------------------------------------------
# Uploaded study material (notes, books, videos ...)
#   Files live in media/ and are NOT served as public URLs: they are streamed through
#   core.views.resource_open, which requires login.
# ---------------------------------------------------------------------------
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))
# How logged-in users get the file:
#   django   - Django streams it (simple; fine for small sites)
#   nginx    - Django checks login, nginx sends the bytes (X-Accel-Redirect: fast + video seeking). Docker setup uses this.
#   redirect - redirect to a short-lived signed URL (S3 / R2 / MinIO)
RESOURCE_SERVE_METHOD = os.environ.get("RESOURCE_SERVE_METHOD", "django")
RESOURCE_ACCEL_PREFIX = os.environ.get("RESOURCE_ACCEL_PREFIX", "/protected-media/")
RESOURCE_MAX_UPLOAD_MB = int(os.environ.get("RESOURCE_MAX_UPLOAD_MB", 100))
# Any file type may be uploaded EXCEPT programs/scripts and web pages (they could run code in a student's browser).
RESOURCE_BLOCKED_EXTENSIONS = {
    "exe", "msi", "bat", "cmd", "com", "scr", "dll", "jar", "apk", "sh", "bash", "ps1", "vbs", "wsf", "lnk",
    "js", "mjs", "php", "phtml", "py", "pl", "cgi", "html", "htm", "xhtml", "svg", "xml", "swf", "hta",
}

# ---------------------------------------------------------------------------
# AI Tutor (optional). Without a key the page still works and suggests related study material.
#   export ANTHROPIC_API_KEY=...   (and optionally AI_TUTOR_MODEL=<model name your key can use>)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_TUTOR_MODEL = os.environ.get("AI_TUTOR_MODEL", "claude-haiku-5-5")
AI_TUTOR_MAX_TOKENS = int(os.environ.get("AI_TUTOR_MAX_TOKENS", 800))
AI_TUTOR_DAILY_LIMIT = int(os.environ.get("AI_TUTOR_DAILY_LIMIT", 20))  # questions per user per day
AI_TUTOR_TIMEOUT = int(os.environ.get("AI_TUTOR_TIMEOUT", 30))

# ---------------------------------------------------------------------------
# Internationalisation / static
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kathmandu"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", BASE_DIR / "staticfiles"))  # `collectstatic` target

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
if not DEBUG and HAS_WHITENOISE:  # hashed + compressed static files (run `collectstatic` first - the Docker image does)
    STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}

# Optional: keep uploads in S3 / Cloudflare R2 / MinIO instead of the server disk (pip install django-storages boto3).
if os.environ.get("AWS_STORAGE_BUCKET_NAME"):
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL") or None  # R2 / MinIO endpoint
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME") or None
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_QUERYSTRING_AUTH = True  # private bucket + signed URLs
    AWS_QUERYSTRING_EXPIRE = int(os.environ.get("AWS_QUERYSTRING_EXPIRE", 300))
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
    RESOURCE_SERVE_METHOD = os.environ.get("RESOURCE_SERVE_METHOD", "redirect")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Production hardening (only when DJANGO_DEBUG=0)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL", True)
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30 if SECURE_SSL_REDIRECT else 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL_REDIRECT
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)  # only enable once you are sure about HTTPS everywhere
    SECURE_REDIRECT_EXEMPT = [r"^healthz/?$", r"^readyz/?$"]  # load balancers / Docker probe over plain HTTP
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    if env_bool("DJANGO_BEHIND_PROXY", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        USE_X_FORWARDED_HOST = True

if "test" in sys.argv[1:2]:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # makes `manage.py test` fast

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Error monitoring (optional): create a free project at sentry.io and set SENTRY_DSN
# ---------------------------------------------------------------------------
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production" if not DEBUG else "development"),
            release=APP_VERSION,
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", 0.1)),
            send_default_pii=False,  # never send passwords / e-mails / IPs of students
        )
    except ImportError:
        logging.getLogger(__name__).warning("SENTRY_DSN is set but sentry-sdk is not installed (pip install sentry-sdk).")
