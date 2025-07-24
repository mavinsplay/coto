from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from upload.models import Video
from upload.validators import validate_video_extension


__all__ = ["SingleVideoForm", "SeriesVideoForm"]


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        return files.getlist(name)


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if len(data) > 20:
            raise ValidationError(_("Можно загрузить максимум 20 файлов."))

        total_size = sum(f.size for f in data)
        max_total_size = 20 * 1024 * 1024 * 1024  # 20 GB
        if total_size > max_total_size:
            raise ValidationError(
                _("Общий размер файлов не должен превышать 20 MB."),
            )

        return data


class SingleVideoForm(forms.ModelForm):
    file = forms.FileField(
        label=_("Видеофайл"),
        validators=[validate_video_extension],
        help_text=_("Поддерживаемые форматы: MP4, AVI, MOV, MKV, WEBM"),
    )

    class Meta:
        model = Video
        fields = ["title", "description", "file", "thumbnail"]
        labels = {
            "title": _("Название фильма"),
            "description": _("Описание фильма"),
            "thumbnail": _("Превью"),
        }


class SeriesVideoForm(forms.ModelForm):
    files = MultipleFileField(
        label=_("Серии"),
        required=False,
        validators=[validate_video_extension],
        help_text=_("Добавьте файлы серий (MP4, AVI, MOV, MKV, WEBM)"),
    )

    class Meta:
        model = Video
        fields = [
            "title",
            "description",
            "thumbnail",
        ]
        labels = {
            "title": _("Название сериий"),
            "description": _("Описание серий"),
            "thumbnail": _("Превью для кажого видео"),
        }
