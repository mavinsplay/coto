import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, TemplateView

from upload.forms import SeriesVideoForm, SingleVideoForm
from upload.models import Video


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
