from django.urls import include, path

from upload.views import (
    SeriesVideoUploadView,
    SingleVideoUploadView,
    UploadOrientationView,
)

app_name = "upload"

urlpatterns = [
    path("", UploadOrientationView.as_view(), name="orientation"),
    path("single/", SingleVideoUploadView.as_view(), name="single_upload"),
    path("series/", SeriesVideoUploadView.as_view(), name="series_upload"),
    path("my/", include("upload.user_chunked_urls")),
]
