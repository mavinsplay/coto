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
        "playlist",
        "host",
        "is_private",
        "get_access_code",
        "created_at",
        "get_thumbnail",
        "count_participants",
    )
    list_filter = ("host", "created_at", "is_private")
    search_fields = (
        "name",
        "host__username",
        "video__title",
        "playlist__title",
        "access_code",
    )
    filter_horizontal = ("participants",)
    readonly_fields = ("get_access_code_display",)

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

    def get_access_code(self, obj):
        if obj.is_private and obj.access_code:
            return format_html(
                '<span style="background-color: #fff\
                    3cd; padding: 4px 8px; border-radius: 4px; '
                'font-weight: bold; font-family: monosp\
                    ace; letter-spacing: 2px;">{}</span>',
                obj.access_code,
            )

        return _("—")

    get_access_code.short_description = _("Код доступа")

    def get_access_code_display(self, obj):
        if obj.is_private and obj.access_code:
            return format_html(
                '<div style="background-color: #fff3cd; padding: 12px; bo\
                    rder-radius: 8px; '
                "font-size: 24px; font-weight: bold; font-family: monosp\
                    ace; letter-spacing: 4px; "
                'text-align: center; margin: 10px 0;">{}</div>',
                obj.access_code,
            )

        return _("Комната не является приватной")

    get_access_code_display.short_description = _(
        "Код доступа (для копирования)",
    )


@admin.register(ChatMessage)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("room", "user", "content", "created_at")
    list_filter = ("room", "user", "created_at")
    search_fields = ("content", "user__username")
    ordering = ("-created_at",)

    def room(self, obj):
        return obj.room.name if obj.room else _("Удалено")

    room.short_description = _("Комната")
