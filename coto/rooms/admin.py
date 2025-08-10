from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from rooms.models import ChatMessage, WatchParty

__all__ = ["WatchPartyAdmin"]


@admin.register(WatchParty)
class WatchPartyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "video",
        "host",
        "created_at",
        "get_thumbnail",
        "count_participants",
    )
    list_filter = ("host", "created_at")
    search_fields = ("name", "host__username", "video__title")
    filter_horizontal = ("participants",)

    def get_thumbnail(self, obj):
        if obj.room_image:
            return format_html(
                '<img src="{}" width="100" height="auto" />',
                obj.room_image.url,
            )

        return _("Нет превью")

    get_thumbnail.short_description = _("предпросмотр превью комнаты")

    def count_participants(self, obj):
        count_participants = obj.participants.count()
        if count_participants == 0:
            return _("Нет участников")

        return f"{count_participants} / {obj.limit_participants}"

    count_participants.short_description = _("количество участников")


@admin.register(ChatMessage)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("room", "user", "content", "created_at")
    list_filter = ("room", "user", "created_at")
    search_fields = ("content", "user__username")
    ordering = ("-created_at",)

    def room(self, obj):
        return obj.room.name if obj.room else _("Удалено")

    room.short_description = _("Комната")
