import logging
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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
    hls_manifest = models.FileField(
        upload_to="videos/hls_manifests/",
        blank=True,
        null=True,
        help_text="Путь до файла master.m3u8",
    )
    hls_progress = models.PositiveSmallIntegerField(default=0)
    hls_status = models.CharField(
        max_length=32,
        blank=True,
        default="awaiting processing",
    )
    hls_log = models.TextField(blank=True, default="")
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
        skip_tasks = kwargs.pop("_skip_tasks", False)
        update_fields = kwargs.get("update_fields")
        is_new = self.pk is None
        if update_fields and self.pk:
            try:
                Video.objects.get(pk=self.pk)
            except Video.DoesNotExist:
                return

        super().save(*args, **kwargs)
        if is_new and not skip_tasks:
            from upload.tasks import extract_video_metadata, generate_hls

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


class Playlist(models.Model):
    """
    Плейлист (сериал, шоу, сборник видео).
    Может содержать сезоны и серии.
    """

    title = models.CharField(_("Название"), max_length=255)
    description = models.TextField(_("Описание"), blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_playlists",
        verbose_name=_("Создал"),
    )
    cover_image = models.ImageField(
        _("Обложка"),
        upload_to="playlists/covers/%Y/%m/%d/",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(_("Дата создания"), default=timezone.now)

    class Meta:
        verbose_name = _("Плейлист")
        verbose_name_plural = _("Плейлисты")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class PlaylistItem(models.Model):
    """
    Связь между плейлистом и видео.
    Можно указывать сезон, номер серии, порядок.
    """

    playlist = models.ForeignKey(
        Playlist,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Плейлист"),
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="in_playlists",
        verbose_name=_("Видео"),
    )
    season_number = models.PositiveIntegerField(_("Сезон"), default=1)
    episode_number = models.PositiveIntegerField(_("Серия"), default=1)
    order = models.PositiveIntegerField(
        _("Порядок"),
        default=0,
        help_text=_("Порядок отображения в плейлисте"),
    )

    class Meta:
        verbose_name = _("Эпизод плейлиста")
        verbose_name_plural = _("Эпизоды плейлиста")
        ordering = ["season_number", "episode_number", "order"]
        unique_together = ("playlist", "season_number", "episode_number")

    def __str__(self):
        return f"{self.playlist.title} — \
            S{self.season_number:02d}E{self.episode_number:02d}"
