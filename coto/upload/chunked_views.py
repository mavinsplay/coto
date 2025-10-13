from pathlib import Path

from chunked_upload.views import ChunkedUploadCompleteView, ChunkedUploadView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from upload.models import Video


__all__ = [
    "AdminChunkedUploadView",
    "AdminChunkedUploadCompleteView",
]


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AdminChunkedUploadView(
    StaffRequiredMixin,
    LoginRequiredMixin,
    ChunkedUploadView,
):
    """
    Нужен для приёма чанков — наследуем поведение из пакета.
    Поле на клиенте должно называться 'file' (field_name ниже).
    """

    field_name = "file"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AdminChunkedUploadCompleteView(
    StaffRequiredMixin,
    LoginRequiredMixin,
    ChunkedUploadCompleteView,
):
    def get_response_data(self, chunked_upload, request=None):
        req = request or getattr(self, "request", None)
        file_field = chunked_upload.file

        title = (
            (req.POST.get("title") if req is not None else None)
            or getattr(chunked_upload, "filename", None)
            or (
                Path(file_field.name).name
                if file_field and file_field.name
                else "file"
            )
        )

        video = Video(
            title=title,
            description=(
                req.POST.get("description", "") if req is not None else ""
            ),
            file=file_field,
            uploaded_by=(req.user if req is not None else None),
        )
        video.save()

        try:
            chunked_upload.delete()
        except Exception:
            pass

        return {
            "video_id": video.pk,
            "video_url": video.file.url,
            "title": video.title,
        }
