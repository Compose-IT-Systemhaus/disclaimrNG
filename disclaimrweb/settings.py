"""Django settings for the disclaimrNG web administration."""

from __future__ import annotations

from pathlib import Path

import environ
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

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
    "django.contrib.humanize",
    "adminsortable2",
    "disclaimrwebadmin.apps.DisclaimrwebadminConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves /static/ directly out of gunicorn so the stack
    # works without a separate nginx/Apache. Must come right after
    # SecurityMiddleware, before everything else, per the WhiteNoise docs.
    "whitenoise.middleware.WhiteNoiseMiddleware",
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

# Django 5+ STORAGES API. WhiteNoise's compressed (non-manifest)
# backend ships gzip/brotli alternates for every static file. We
# can't use the *Manifest* variant because the template editor's
# vendored Monaco/TinyMCE assets are referenced from JS with
# hard-coded ``/static/...`` paths, which the manifest backend would
# rename with a hash suffix and break.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

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
                "django.template.context_processors.request",
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
    # The admin *is* the site — no "Return to site" / "View site" links.
    "SITE_URL": None,
    "SITE_SUBHEADER": _("Mail signature server"),
    # Square brand mark next to the site name in the sidebar (the wide
    # wordmark logo is used on the login page). Lazy callables — unfold
    # resolves them at request time, once the static finder is wired up.
    "SITE_ICON": lambda request: static("disclaimrwebadmin/img/mark.svg"),
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "type": "image/svg+xml",
            "href": lambda request: static("disclaimrwebadmin/img/mark.svg"),
        },
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "BORDER_RADIUS": "8px",
    # Dashboard figures, setup checklist and recent changes on the index.
    "DASHBOARD_CALLBACK": "disclaimrwebadmin.dashboard.dashboard_callback",
    "LOGIN": {
        "image": lambda request: static("disclaimrwebadmin/img/login_panel.svg"),
    },
    # Neutral zinc chrome with the navy of the logo as the only accent.
    # Primary drives buttons, links and focus rings; base the sidebar,
    # cards and dividers. Tailwind 50–950 ramps as django-unfold expects.
    "COLORS": {
        "base": {
            "50": "#fafafa",
            "100": "#f4f4f5",
            "200": "#e4e4e7",
            "300": "#d4d4d8",
            "400": "#a1a1aa",
            "500": "#71717a",
            "600": "#52525b",
            "700": "#3f3f46",
            "800": "#27272a",
            "900": "#18181b",
            "950": "#09090b",
        },
        "primary": {
            "50": "#f1f5fa",
            "100": "#e2eaf4",
            "200": "#c5d5e9",
            "300": "#9bb6d8",
            "400": "#6a90c1",
            "500": "#4772a8",
            "600": "#345a8c",
            "700": "#2b4a72",
            "800": "#263f5f",
            "900": "#22354f",
            "950": "#162235",
        },
    },
    # Shared design tokens plus the bits of chrome unfold doesn't cover.
    "STYLES": [
        lambda request: static("disclaimrwebadmin/css/admin_chrome.css"),
        lambda request: static("disclaimrwebadmin/css/language_switcher.css"),
        lambda request: static("disclaimrwebadmin/css/help_button.css"),
    ],
    "SCRIPTS": [
        lambda request: static("disclaimrwebadmin/js/language_switcher.js"),
        lambda request: static("disclaimrwebadmin/js/help_button.js"),
    ],
    # Hand-curated sidebar — explicit groups in the order operators
    # think about them, with German labels matching the rest of the UI.
    # Setting ``navigation`` overrides Django's default app/model
    # auto-grouping, so anything not listed here is hidden from the
    # sidebar (still reachable by URL).
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": _("Signatures"),
                "separator": True,
                "items": [
                    {
                        "title": _("Manage signatures"),
                        "icon": "draw",
                        "link": reverse_lazy(
                            "admin:disclaimrwebadmin_disclaimer_changelist"
                        ),
                    },
                    {
                        "title": _("Rules"),
                        "icon": "rule",
                        "link": reverse_lazy(
                            "admin:disclaimrwebadmin_rule_changelist"
                        ),
                    },
                    {
                        "title": _("Images"),
                        "icon": "image",
                        "link": reverse_lazy(
                            "admin:disclaimrwebadmin_signatureimage_changelist"
                        ),
                    },
                    {
                        "title": _("Signature test"),
                        "icon": "science",
                        "link": reverse_lazy(
                            "disclaimrwebadmin:signature-test"
                        ),
                    },
                ],
            },
            {
                "title": _("Settings"),
                "separator": True,
                "items": [
                    {
                        "title": _("Tenants"),
                        "icon": "groups",
                        "link": reverse_lazy(
                            "admin:disclaimrwebadmin_tenant_changelist"
                        ),
                    },
                    {
                        "title": _("Directory servers"),
                        "icon": "dns",
                        "link": reverse_lazy(
                            "admin:disclaimrwebadmin_directoryserver_changelist"
                        ),
                    },
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                    },
                    {
                        "title": _("Groups"),
                        "icon": "group",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
        ],
    },
}

# Available languages for the in-admin language switcher.
LANGUAGES = [
    ("en", _("English")),
    ("de", _("German")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

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
