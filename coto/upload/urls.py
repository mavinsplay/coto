from django.urls import path

from upload.views import (
    AdminChunkedUploadCompleteView,
    AdminChunkedUploadView,
    SeriesVideoUploadView,
    SingleVideoUploadView,
    UploadOrientationView,
)

app_name = "upload"

urlpatterns = [
    path("", UploadOrientationView.as_view(), name="orientation"),
    path("single/", SingleVideoUploadView.as_view(), name="single_upload"),
    path("series/", SeriesVideoUploadView.as_view(), name="series_upload"),
    path(
        "chunked-upload/",
        AdminChunkedUploadView.as_view(),
        name="chunked_upload",
    ),
    path(
        "chunked-upload/complete/",
        AdminChunkedUploadCompleteView.as_view(),
        name="chunked_upload_complete",
    ),
]
