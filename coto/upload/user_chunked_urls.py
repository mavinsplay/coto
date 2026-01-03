from django.urls import path

from upload.user_chunked_views import (
    PlaylistVideosView,
    UpdatePlaylistOrderView,
    UpdateVideoMetadataView,
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
    path(
        "playlist/<int:playlist_id>/videos/",
        PlaylistVideosView.as_view(),
        name="playlist_videos",
    ),
    path(
        "playlist/update-order/",
        UpdatePlaylistOrderView.as_view(),
        name="update_playlist_order",
    ),
    path(
        "video/<int:video_id>/update/",
        UpdateVideoMetadataView.as_view(),
        name="update_video_metadata",
    ),
]
