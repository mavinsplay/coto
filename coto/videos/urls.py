from django.urls import path

from videos.views import (
    MyVideosListView,
    VideoDeleteView,
    VideoDetailView,
    VideoUpdateView,
)

app_name = "videos"

urlpatterns = [
    path("", MyVideosListView.as_view(), name="list"),
    path("<int:pk>/", VideoDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", VideoUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", VideoDeleteView.as_view(), name="delete"),
]
