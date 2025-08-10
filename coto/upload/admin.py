from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from upload.models import Playlist, PlaylistItem, Video


__all__ = ["VideoAdmin"]


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "get_thumbnail",
        "uploaded_by",
        "created_at",
        "get_human_duration",
        "get_human_filesize",
    )
    list_filter = ("uploaded_by", "created_at")
    search_fields = ("title", "description", "uploaded_by__username")
    readonly_fields = (
        "get_video_preview",
        "get_thumbnail",
        "get_human_duration",
    )
    fieldsets = (
        (
            _("Основная информация"),
            {"fields": ("title", "description", "uploaded_by")},
        ),
        (
            _("Медиа"),
            {
                "fields": (
                    "file",
                    "get_video_preview",
                    "thumbnail",
                    "get_thumbnail",
                ),
            },
        ),
        (
            _("Статистика"),
            {"fields": ("get_human_duration", "created_at")},
        ),
    )

    def get_thumbnail(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" width="100" height="auto" />',
                obj.thumbnail.url,
            )

        return _("Нет превью")

    get_thumbnail.short_description = _("предпросмотр превью")

    def get_video_preview(self, obj):
        if obj.file:
            return format_html(
                """
                <video width="320" height="240" controls>
                    <source src="{}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
                """,
                obj.file.url,
            )

        return _("Видео не загружено")

    get_video_preview.short_description = _("Предпросмотр видео")

    def get_human_duration(self, obj):
        if not obj.duration:
            return _("не указано")

        total_seconds = int(obj.duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if hours:
            parts.append(_("%d час%s") % (hours, "" if hours == 1 else "а"))

        if minutes:
            parts.append(
                _("%d минут%s")
                % (
                    minutes,
                    "а" if 2 <= minutes <= 4 else "" if minutes == 1 else "",
                ),
            )

        if seconds or not parts:
            parts.append(
                _("%d секунд%s")
                % (
                    seconds,
                    "ы" if 2 <= seconds <= 4 else "" if seconds == 1 else "",
                ),
            )

        return " ".join(parts)

    get_human_duration.short_description = _("Длительность")

    def get_human_filesize(self, obj):
        size = obj.file_size
        if size is None:
            return _("неизвестно")

        units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
        for unit in units:
            if size < 1024.0:
                return f"{size:.1f} {unit}"

            size /= 1024.0

        return f"{size:.1f} ПБ"

    get_human_filesize.short_description = _("Размер файла")


class PlaylistItemInline(admin.TabularInline):
    model = PlaylistItem
    extra = 1
    fields = ("season_number", "episode_number", "video", "order")
    ordering = ("season_number", "episode_number", "order")
    autocomplete_fields = ["video"]
    show_change_link = True


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ("title", "created_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "description", "created_by__username")
    inlines = [PlaylistItemInline]
    autocomplete_fields = ["created_by"]
    date_hierarchy = "created_at"


@admin.register(PlaylistItem)
class PlaylistItemAdmin(admin.ModelAdmin):
    list_display = (
        "playlist",
        "season_number",
        "episode_number",
        "video",
        "order",
    )
    list_filter = ("playlist", "season_number")
    search_fields = (
        "playlist__title",
        "video__title",
    )
    ordering = ("playlist", "season_number", "episode_number", "order")
    autocomplete_fields = ["playlist", "video"]
