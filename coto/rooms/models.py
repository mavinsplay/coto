from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

from upload.models import Playlist, Video

__all__ = ["WatchParty"]


class WatchParty(models.Model):
    name = models.CharField(_("Название комнаты"), max_length=200)

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="watch_parties",
        verbose_name=_("Видео"),
        blank=True,
        null=True,
    )
    playlist = models.ForeignKey(
        Playlist,
        on_delete=models.CASCADE,
        related_name="watch_parties",
        verbose_name=_("Плейлист"),
        blank=True,
        null=True,
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
        verbose_name=_("Лимит участников"),
    )
    is_private = models.BooleanField(
        verbose_name=_("Приватная"),
        default=False,
    )
    current_time = models.FloatField(_("Текущее время видео"), default=0.0)
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True)

    class Meta:
        verbose_name = _("Комната просмотра")
        verbose_name_plural = _("Комнаты просмотра")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        """Проверяем, что выбрано либо видео, либо плейлист, но не оба."""
        from django.core.exceptions import ValidationError

        if not self.video and not self.playlist:
            raise ValidationError(_("Выберите либо видео, либо плейлист."))

        if self.video and self.playlist:
            raise ValidationError(
                _("Нельзя выбрать и видео, и плейлист одновременно."),
            )

    @property
    def content_type(self):
        if self.video:
            return "video"

        if self.playlist:
            return "playlist"

        return None


class ChatMessage(models.Model):
    room = models.ForeignKey(
        "rooms.WatchParty",
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("Комната"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("пользователь"),
    )
    content = models.TextField(verbose_name=_("Собщение"))
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Сообщение чата")
        verbose_name_plural = _("Сообщений чата")

    def __str__(self):
        return f"[{self.room}] {self.user}: {self.content[:20]}"
