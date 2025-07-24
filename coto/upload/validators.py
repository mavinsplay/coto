from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


__all__ = ["validate_video_extension"]


def validate_video_extension(value):
    ext = Path(value.name).suffix
    valid_extensions = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
    if not ext.lower() in valid_extensions:
        raise ValidationError(
            _("Поддерживаются только видеофайлы: {}").format(
                ", ".join(valid_extensions),
            ),
        )
