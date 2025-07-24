from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

__all__ = ["Video", "WatchParty"]


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

    class Meta:
        verbose_name = _("Видео")
        verbose_name_plural = _("Видео")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class WatchParty(models.Model):
    name = models.CharField(_("Название комнаты"), max_length=200)
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="watch_parties",
        verbose_name=_("Видео"),
    )
    host = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="hosted_parties",
        verbose_name=_("Организатор"),
    )
    participants = models.ManyToManyField(
        User,
        related_name="joined_parties",
        verbose_name=_("Участники"),
    )
    current_time = models.FloatField(_("Текущее время видео"), default=0.0)
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True)

    class Meta:
        verbose_name = _("Комната просмотра")
        verbose_name_plural = _("Комнаты просмотра")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
