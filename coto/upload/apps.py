from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


__all__ = ["UploadConfig"]


class UploadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "upload"
    verbose_name = _("Загрузка видео")

    def ready(self):
        import upload.signals  # noqa
