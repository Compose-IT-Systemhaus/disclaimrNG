"""Django settings for the disclaimrNG web administration."""

from __future__ import annotations

from pathlib import Path

import environ
from django.templatetags.static import static

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["*"]),
    DJANGO_TIME_ZONE=(str, "UTC"),
    DJANGO_LANGUAGE_CODE=(str, "en-us"),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, []),
    MEDIA_BASE_URL=(str, ""),
)

env_file = BASE_DIR / ".env"
if env_file.is_file():
    environ.Env.read_env(env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    # django-unfold must precede django.contrib.admin so its templates win.
    "unfold",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "adminsortable2",
    "disclaimrwebadmin",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "disclaimrweb.urls"
WSGI_APPLICATION = "disclaimrweb.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://disclaimr:disclaimr@db:5432/disclaimr"),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE")
TIME_ZONE = env("DJANGO_TIME_ZONE")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

# Public absolute base URL prepended to media file paths when rendered into
# emails (signatures fly through MTAs, so relative URLs are useless). Falls
# back to MEDIA_URL for local development; in production set this to the
# public hostname of your disclaimrNG deployment.
MEDIA_BASE_URL = env("MEDIA_BASE_URL").rstrip("/") or MEDIA_URL.rstrip("/")

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "django.contrib.staticfiles.finders.FileSystemFinder",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

UNFOLD = {
    "SITE_TITLE": "disclaimrNG",
    "SITE_HEADER": "disclaimrNG",
    "SITE_URL": "/",
    # Logo as a lazy callable — django-unfold resolves it at request time so
    # the static finder is fully wired before static() runs. Transparent
    # PNGs so the chrome shows through cleanly in both themes.
    "SITE_LOGO": {
        "light": lambda request: static("disclaimrwebadmin/img/logo_light_mode.png"),
        "dark": lambda request: static("disclaimrwebadmin/img/logo_dark_mode.png"),
    },
    "SITE_ICON": {
        "light": lambda request: static("disclaimrwebadmin/img/logo_light_mode.png"),
        "dark": lambda request: static("disclaimrwebadmin/img/logo_dark_mode.png"),
    },
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    # Calm steel-blue accent on a near-neutral slate base. Primary is the
    # accent (used for buttons, links, focus rings); base is the chrome
    # (sidebar, cards, dividers). Both palettes use the Tailwind 50–950
    # ramp django-unfold expects, expressed as space-separated R G B so
    # the same definition works in light and dark mode.
    "COLORS": {
        "base": {
            "50": "248 250 252",
            "100": "241 245 249",
            "200": "226 232 240",
            "300": "203 213 225",
            "400": "148 163 184",
            "500": "100 116 139",
            "600": "71 85 105",
            "700": "51 65 85",
            "800": "30 41 59",
            "900": "15 23 42",
            "950": "2 6 23",
        },
        "primary": {
            "50": "239 246 255",
            "100": "219 234 254",
            "200": "191 219 254",
            "300": "147 197 253",
            "400": "96 165 250",
            "500": "59 130 246",
            "600": "37 99 235",
            "700": "29 78 216",
            "800": "30 64 175",
            "900": "30 58 138",
            "950": "23 37 84",
        },
    },
    # A pinch of bespoke CSS to lighten visual weight: thinner borders,
    # softer shadows, slightly more breathing room around form rows.
    "STYLES": [
        lambda request: static("disclaimrwebadmin/css/admin_chrome.css"),
    ],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "disclaimr": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}
