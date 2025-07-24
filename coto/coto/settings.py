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

SITE_URL = os.getenv("DJANGO_SITE_URL", "http://127.0.0.1:8000")

DEFAULT_USER_IS_ACTIVE = utils.get_bool_env(
    os.getenv("DJANGO_DEFAULT_USER_IS_ACTIVE", "true" if DEBUG else "false"),
)

MAIL = os.getenv("DJANGO_MAIL", "example@mail.com")

EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "smtp.gmail.com")
EMAIL_HOST_PASSWORD = os.getenv(
    "DJANGO_EMAIL_HOST_PASSWORD",
    "",
)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = MAIL
EMAIL_USE_TLS = True
EMAIL_HOST_USER = MAIL
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


INSTALLED_APPS = [
    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "catalog.apps.CatalogConfig",
    "homepage.apps.HomepageConfig",
    "users.apps.UsersConfig",
    "upload.apps.UploadConfig",
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

WSGI_APPLICATION = "coto.wsgi.application"


SELECTED_DATABASE = os.getenv(
    "DJANGO_DATABASE_SELECT",
    "postgresql" if not DEBUG else "sqlite3",
)

if SELECTED_DATABASE == "postgresql":
    DB_NAME = os.getenv("DJANGO_POSTGRESQL_NAME", "lambda_search")
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

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
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
            "level": "DEBUG" if DEBUG else "WARNING",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "verbose" if DEBUG else "simple",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "upload": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": False,
        },
    },
}


if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INSTALLED_APPS.insert(0, "debug_toolbar")
    INTERNAL_IPS = [
        "127.0.0.1",
    ]
