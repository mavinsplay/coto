from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

from upload.models import Video

__all__ = ["WatchParty"]


class WatchParty(models.Model):
    name = models.CharField(_("Название комнаты"), max_length=200)
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="watch_parties",
        verbose_name=_("Видео"),
    )
    room_image = models.ImageField(
        verbose_name=_("Изображение комнаты"),
        upload_to="thumbnails/rooms_images/%Y/%m/%d/",
        blank=True,
        default=None,
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
        blank=True,
    )
    limit_participants = models.IntegerField(
        default=10,
        verbose_name=_("Участники"),
    )
    is_private = models.BooleanField(
        verbose_name=_("Приватная"),
    )
    current_time = models.FloatField(_("Текущее время видео"), default=0.0)
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True)

    class Meta:
        verbose_name = _("Комната просмотра")
        verbose_name_plural = _("Комнаты просмотра")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
