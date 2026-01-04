"""
Simplified URLs for testing - excludes problematic apps
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

__all__ = []


# Dummy view for testing
class DummyView(TemplateView):
    template_name = "base.html"


# Dummy URL patterns for excluded apps
upload_dummy_patterns = [
    path("orientation/", DummyView.as_view(), name="orientation"),
    path("user-upload/", DummyView.as_view(), name="user-upload"),
]

rooms_dummy_patterns = [
    path("", DummyView.as_view(), name="list"),
    path("manage/", DummyView.as_view(), name="manage"),
    path("<int:pk>/", DummyView.as_view(), name="detail"),
]

videos_dummy_patterns = [
    path("", DummyView.as_view(), name="list"),
    path("<int:pk>/", DummyView.as_view(), name="detail"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("homepage.urls")),
    path("auth/", include("users.urls")),
    # Dummy namespaces for excluded apps
    path(
        "upload/",
        include((upload_dummy_patterns, "upload"), namespace="upload"),
    ),
    path(
        "rooms/",
        include((rooms_dummy_patterns, "rooms"), namespace="rooms"),
    ),
    path(
        "videos/",
        include((videos_dummy_patterns, "videos"), namespace="videos"),
    ),
]
