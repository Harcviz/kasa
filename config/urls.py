"""Root URL routing for the project."""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from ledger.views import SuperuserLoginView

urlpatterns = [
    path("login/", SuperuserLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("ledger.urls")),
    path("admin/", admin.site.urls),
]
