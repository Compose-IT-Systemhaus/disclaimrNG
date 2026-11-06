from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import include, path, re_path
from django.views.i18n import JavaScriptCatalog
from django.views.static import serve

from .health import healthz


def media(request: HttpRequest, path: str) -> HttpResponse:
    # shortcut: served by gunicorn — fine for a few small, public signature
    # images; put nginx/Caddy in front of MEDIA_URL if image traffic grows.
    # Read MEDIA_ROOT per request (not at import) so it can be overridden.
    return serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    # Django's built-in language switch endpoint — POST'd by the
    # flag toggle in the topbar and stores the choice in the
    # ``django_language`` cookie + session.
    path("i18n/", include("django.conf.urls.i18n")),
    # gettext() for our topbar scripts; domain "django" because our strings
    # live in django.po (the default "djangojs" would need a second catalog).
    path("i18n/js/", JavaScriptCatalog.as_view(domain="django"), name="jsi18n"),
    # Signature images are embedded in mails, so recipients must reach them
    # without a login — in production too, not only with DEBUG.
    re_path(rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.*)$", media),
    path("healthz", healthz),
    path("admin/disclaimr/", include("disclaimrwebadmin.urls")),
]

if settings.OIDC_ENABLED:
    # Only the login and callback of the OpenID Connect provider — not allauth's account pages
    # (sign-up, password reset, ...), which would open a second way in.
    urlpatterns.append(
        path("accounts/", include("allauth.socialaccount.providers.openid_connect.urls"))
    )

urlpatterns.append(path("", admin.site.urls))
