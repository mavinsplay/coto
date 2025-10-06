import json
import logging

from chunked_upload.models import ChunkedUpload
from chunked_upload.views import ChunkedUploadCompleteView, ChunkedUploadView
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, TemplateView

from upload.forms import SeriesVideoForm, SingleVideoForm
from upload.models import Video


logger = logging.getLogger(__name__)


__all__ = [
    "UploadOrientationView",
    "SingleVideoUploadView",
    "SeriesVideoUploadView",
]


class UploadOrientationView(TemplateView, LoginRequiredMixin):
    template_name = "upload/orientation.html"


class SingleVideoUploadView(CreateView, LoginRequiredMixin):
    model = Video
    form_class = SingleVideoForm
    template_name = "upload/modals/single_upload_modal.html"

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        self.object = form.save()
        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": json.dumps(
                    {
                        "videoUploaded": None,
                        "showMessage": _("Видео успешно загружено"),
                    },
                ),
            },
        )


class SeriesVideoUploadView(CreateView, LoginRequiredMixin):
    model = Video
    form_class = SeriesVideoForm
    template_name = "upload/modals/series_upload_modal.html"

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        self.object = form.save()
        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": json.dumps(
                    {
                        "videoUploaded": None,
                        "showMessage": _("Серия успешно загружена"),
                    },
                ),
            },
        )


@method_decorator(staff_member_required, name="dispatch")
class AdminChunkedUploadView(ChunkedUploadView):
    model = ChunkedUpload
    field_name = "file"


@method_decorator(staff_member_required, name="dispatch")
class AdminChunkedUploadCompleteView(ChunkedUploadCompleteView):
    model = ChunkedUpload

    def get_response_data(self, *args, **kwargs):
        """
        Поддерживаем обе сигнатуры:
          - get_response_data(self, chunked_upload)
          - get_response_data(self, request, chunked_upload)

        Возвращаем словарь, который библиотека преобразует в JSON-ответ.
        """

        if len(args) == 1:
            chunked_upload = args[0]

        elif len(args) == 2:
            chunked_upload = args[1]
        else:
            logger.error(
                "get_response_data called with unexpected args: %r kwargs=%r",
                args,
                kwargs,
            )
            raise TypeError("Unexpected get_response_data signature")

        try:
            chunked_path = (
                chunked_upload.file.name
                if getattr(chunked_upload, "file", None)
                else ""
            )
        except Exception as exc:
            logger.exception(
                "Error while accessing chunked_upload.file: %s",
                exc,
            )
            chunked_path = ""

        return {"chunked_path": chunked_path}

    def post(self, request, *args, **kwargs):
        logger.debug(
            "AdminChunkedUploadComplete\
                View POST: POST keys=%s META_CONTENT_RANGE=%s",
            list(request.POST.keys()),
            request.META.get("HTTP_CONTENT_RANGE"),
        )
        return super().post(request, *args, **kwargs)
