from datetime import timedelta
import os
from pathlib import Path
import sys

from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

from coto import utils


__all__ = ()

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-lwb6t*qe&)j(zkje%3d@2)jyk+5c-ks_se_m5^#0z*5z$e&cw3",
)

DEBUG = utils.get_bool_env(os.getenv("DJANGO_DEBUG", "true"))

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "coto-o2o.ru").split(
    ",",
)

CSRF_TRUSTED_ORIGINS = os.getenv(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://cotoo.ru",
).split(",")

SITE_URL = os.getenv("DJANGO_SITE_URL", "http://127.0.0.1:8000")
SITE_NAME = os.getenv("DJANGO_SITE_NAME", "Coto")

# User activation settings
DEFAULT_USER_IS_ACTIVE = utils.get_bool_env(
    os.getenv("DJANGO_DEFAULT_USER_IS_ACTIVE", "true" if DEBUG else "false"),
)

# Email Configuration - Load from .env
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
EMAIL_USE_TLS = utils.get_bool_env(os.getenv("DJANGO_EMAIL_USE_TLS", "true"))
EMAIL_USE_SSL = utils.get_bool_env(os.getenv("DJANGO_EMAIL_USE_SSL", "false"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv(
    "DJANGO_DEFAULT_FROM_EMAIL",
    os.getenv("DJANGO_EMAIL_HOST_USER", "noreply@example.com"),
)
SERVER_EMAIL = os.getenv("DJANGO_SERVER_EMAIL", DEFAULT_FROM_EMAIL)

# Legacy support (deprecated, use EMAIL_HOST_USER instead)
MAIL = EMAIL_HOST_USER

# Cloudflare Turnstile CAPTCHA Configuration
TURNSTILE_ENABLED = utils.get_bool_env(os.getenv("TURNSTILE_ENABLED", "false"))
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CHUNKED_UPLOAD_EXPIRATION_DELTA = timedelta(days=1)
CHUNKED_UPLOAD_PATH = "chunked_uploads/%Y/%m/%d"
CHUNKED_UPLOAD_TO = CHUNKED_UPLOAD_PATH + "/%Y/%m/%d.part"
CHUNKED_UPLOAD_MAX_BYTES = None

INSTALLED_APPS = [
    # Third-party apps
    "daphne",
    "channels",
    "chunked_upload",
    "sorl.thumbnail",
    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "homepage.apps.HomepageConfig",
    "users.apps.UsersConfig",
    "upload.apps.UploadConfig",
    "rooms.apps.RoomsConfig",
    "videos.apps.VideosConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
]

# Authentication backends
AUTHENTICATION_BACKENDS = [
    "users.backends.EmailOrUsernameModelBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Security settings
MAX_AUTH_ATTEMPTS = int(os.getenv("MAX_AUTH_ATTEMPTS", "10"))
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

ROOT_URLCONF = "coto.urls"

template_dirs = [BASE_DIR / "templates"]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": template_dirs,
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "coto.asgi.application"

SELECTED_DATABASE = os.getenv(
    "DJANGO_DATABASE_SELECT",
    "postgresql" if not DEBUG else "sqlite3",
)

if SELECTED_DATABASE == "postgresql":
    DB_NAME = os.getenv("DJANGO_POSTGRESQL_NAME", "coto_db")
    DB_USER = os.getenv("DJANGO_POSTGRESQL_USER", "postgres")
    DB_PASSWORD = os.getenv("DJANGO_POSTGRESQL_PASSWORD", "root")
    DB_HOST = os.getenv("DJANGO_POSTGRESQL_HOST", "localhost")
    DB_PORT = int(os.getenv("DJANGO_POSTGRESQL_PORT", "5432"))

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": DB_NAME,
            "USER": DB_USER,
            "PASSWORD": DB_PASSWORD,
            "HOST": DB_HOST,
            "PORT": DB_PORT,
        },
    }

else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        },
    }

# Use SQLite for tests (faster and no permissions needed)
if "test" in sys.argv:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",  # In-memory database for tests
        },
    }
    PROBLEMATIC_APPS = [
        "chunked_upload",
        "upload.apps.UploadConfig",
        "rooms.apps.RoomsConfig",  # Depends on upload
        "videos.apps.VideosConfig",  # Depends on upload
        "debug_toolbar",  # Causes URL issues in tests
    ]
    INSTALLED_APPS = [
        app for app in INSTALLED_APPS if app not in PROBLEMATIC_APPS
    ]

    # Use simplified URLs for tests
    ROOT_URLCONF = "coto.test_urls"

    # Disable migrations for tests (faster)
    class DisableMigrations:
        def __contains__(self, item):
            return True

        def __getitem__(self, item):
            return None

    # Disable email sending during tests
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    # Disable Turnstile for tests
    TURNSTILE_ENABLED = False

    # Simplify password hashing for faster tests
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password"
        "_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password"
        "_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password"
        "_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password"
        "_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "ru"

LANGUAGES = [
    ("en-US", _("English")),
    ("ru-RU", _("Russian")),
]

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = LOGIN_URL


STATIC_ROOT = BASE_DIR / "static"

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static_dev",
]

MEDIA_ROOT = BASE_DIR / "media"

MEDIA_URL = "/media/"

LANGUAGES = [
    ("en", "English"),
    ("ru", "Russian"),
]

LOCALE_PATHS = [
    BASE_DIR / "locale",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DEBUG_LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "colored": {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s[%(levelname)s] %(asctime)s %(name)s: %(message)s",  # noqa: E501
            "log_colors": {
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
            "style": "%",
        },
        "verbose": {
            "format": "[{levelname}] {asctime} {name}: {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{levelname}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "colored" if DEBUG else "simple",
            "level": DEBUG_LOG_LEVEL,
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "debug.log",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"] if DEBUG else ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "upload": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": False,
        },
        "rooms": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# redis URI с учётом пароля
if REDIS_PASSWORD:
    REDIS_URI = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/\
    {REDIS_DB}"
else:
    REDIS_URI = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# celery
CELERY_BROKER_URL = REDIS_URI
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"

# cache
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URI,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "PASSWORD": REDIS_PASSWORD,
        },
    },
}

# channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URI],
        },
    },
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 0

DATA_UPLOAD_MAX_MEMORY_SIZE = None


if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INSTALLED_APPS.insert(0, "debug_toolbar")
    INTERNAL_IPS = [
        "127.0.0.1",
    ]
