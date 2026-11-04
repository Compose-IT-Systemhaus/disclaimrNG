from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog

urlpatterns = [
    # Django's built-in language switch endpoint — POST'd by the
    # flag toggle in the topbar and stores the choice in the
    # ``django_language`` cookie + session.
    path("i18n/", include("django.conf.urls.i18n")),
    # gettext() for our topbar scripts; domain "django" because our strings
    # live in django.po (the default "djangojs" would need a second catalog).
    path("i18n/js/", JavaScriptCatalog.as_view(domain="django"), name="jsi18n"),
    path("admin/disclaimr/", include("disclaimrwebadmin.urls")),
    path("", admin.site.urls),
]

# Serve uploaded signature images during development. In production a
# reverse proxy (nginx, Caddy, …) should handle MEDIA_URL directly.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
