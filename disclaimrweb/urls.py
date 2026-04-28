from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django's built-in language switch endpoint — POST'd by the
    # flag toggle in the topbar and stores the choice in the
    # ``django_language`` cookie + session.
    path("i18n/", include("django.conf.urls.i18n")),
    path("admin/disclaimr/", include("disclaimrwebadmin.urls")),
    path("", admin.site.urls),
]

# Serve uploaded signature images during development. In production a
# reverse proxy (nginx, Caddy, …) should handle MEDIA_URL directly.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
