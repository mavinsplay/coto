from django.urls import path

from upload.user_chunked_views import (
    UserChunkedUploadCompleteView,
    UserChunkedUploadView,
    UserUploadPageView,
)

urlpatterns = [
    path(
        "",
        UserUploadPageView.as_view(),
        name="user_upload_page",
    ),
    path(
        "chunked/start/",
        UserChunkedUploadView.as_view(),
        name="user_chunked_upload_start",
    ),
    path(
        "chunked/complete/",
        UserChunkedUploadCompleteView.as_view(),
        name="user_chunked_upload_complete",
    ),
]
