from django.urls import path

from upload.chunked_views import (
    AdminChunkedUploadCompleteView,
    AdminChunkedUploadView,
)

urlpatterns = [
    path(
        "start/",
        AdminChunkedUploadView.as_view(),
        name="chunked_upload_start",
    ),
    path(
        "complete/",
        AdminChunkedUploadCompleteView.as_view(),
        name="chunked_upload_complete",
    ),
]
