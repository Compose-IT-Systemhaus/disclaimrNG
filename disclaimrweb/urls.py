from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/disclaimr/", include("disclaimrwebadmin.urls")),
    path("", admin.site.urls),
]

# Serve uploaded signature images during development. In production a
# reverse proxy (nginx, Caddy, …) should handle MEDIA_URL directly.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
