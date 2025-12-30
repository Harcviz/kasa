"""Root URL routing for the project."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("ledger.urls")),
    path("admin/", admin.site.urls),
]
