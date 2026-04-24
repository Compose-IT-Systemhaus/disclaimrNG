from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/disclaimr/", include("disclaimrwebadmin.urls")),
    path("", admin.site.urls),
]
