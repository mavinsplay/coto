import logging
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from upload.tasks import extract_video_metadata, generate_hls

__all__ = "Video"


logger = logging.getLogger(__name__)


class Video(models.Model):
    title = models.CharField(_("Название"), max_length=200)
    description = models.TextField(_("Описание"), blank=True)
    file = models.FileField(_("Видеофайл"), upload_to="videos/%Y/%m/%d/")
    thumbnail = models.ImageField(
        _("Превью"),
        upload_to="thumbnails/%Y/%m/%d/",
        blank=True,
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="uploaded_videos",
        verbose_name=_("Загрузил"),
    )
    created_at = models.DateTimeField(_("Дата загрузки"), default=timezone.now)
    duration = models.DurationField(_("Длительность"), null=True, blank=True)
    views = models.PositiveIntegerField(_("Просмотры"), default=0)
    hls_manifest = models.FileField(
        upload_to="videos/hls_manifests/",
        blank=True,
        null=True,
        help_text="Путь до файла master.m3u8",
    )
    file_size = models.BigIntegerField(
        _("Размер файла (в байтах)"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Видео")
        verbose_name_plural = _("Видео")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new:
            extract_video_metadata.delay(self.pk)
            generate_hls.delay(self.pk)

    def delete(self, *args, **kwargs):
        if self.file and default_storage.exists(self.file.name):
            try:
                default_storage.delete(self.file.name)
                logger.info("Удалён видеофайл: %s", self.file.name)
            except Exception as e:
                logger.error(
                    "Ошибка при удалении видеофайла '%s': %s",
                    self.file.name,
                    e,
                    exc_info=True,
                )

        if self.hls_manifest and default_storage.exists(
            self.hls_manifest.name,
        ):
            try:
                default_storage.delete(self.hls_manifest.name)
                logger.info("Удалён HLS manifest: %s", self.hls_manifest.name)

                manifest_path = Path(self.hls_manifest.name)
                manifest_dir = manifest_path.parent
                try:
                    _, files = default_storage.listdir(str(manifest_dir))
                    for filename in files:
                        if filename.endswith(".ts"):
                            filepath = manifest_dir / filename
                            if default_storage.exists(str(filepath)):
                                default_storage.delete(str(filepath))
                                logger.info("Удалён сегмент: %s", filepath)
                except NotImplementedError:
                    logger.warning(
                        "listdir не поддерживается в storage, \
                            сегменты не удалены.",
                    )
            except Exception as e:
                logger.error(
                    "Ошибка при удалении HLS файлов в '%s': %s",
                    self.hls_manifest.name,
                    e,
                    exc_info=True,
                )

        super().delete(*args, **kwargs)
