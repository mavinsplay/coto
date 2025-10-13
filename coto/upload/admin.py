from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from upload.models import Playlist, PlaylistItem, Video
from upload.widgets import ChunkedAdminFileWidget


__all__ = ["VideoAdmin"]


class VideoAdminForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = "__all__"
        widgets = {
            "file": ChunkedAdminFileWidget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "file" in self.fields:
            self.fields["file"].required = False

    def clean_file(self):
        file_field = self.cleaned_data.get("file")
        upload_id = self.data.get("file_upload_id")
        if upload_id:
            try:
                video = Video.objects.get(pk=upload_id)
                return video.file
            except Video.DoesNotExist:
                pass

        if not self.instance.pk and not file_field and not upload_id:
            raise ValidationError("Необходимо загрузить файл")

        if self.instance.pk and not file_field:
            return self.instance.file

        return file_field

    def save(self, commit=True):
        upload_id = self.data.get("file_upload_id")
        if upload_id and not self.instance.pk:
            try:
                existing = Video.objects.get(pk=upload_id)
            except Video.DoesNotExist:
                return super().save(commit=commit)

            self.instance = existing
            cd = self.cleaned_data
            if cd.get("title"):
                existing.title = cd.get("title")

            existing.description = (
                cd.get("description")
                if "description" in cd
                else existing.description
            )

            if "uploaded_by" in cd and cd.get("uploaded_by") is not None:
                existing.uploaded_by = cd.get("uploaded_by")

            if cd.get("file"):
                existing.file = cd.get("file")

            # Если загрузили миниатюру через форму — обновим
            if cd.get("thumbnail"):
                existing.thumbnail = cd.get("thumbnail")

            if commit:
                existing.save()
                try:
                    super().save_m2m()
                except Exception:
                    pass

            return existing

        return super().save(commit=commit)

    def save_m2m(self):
        try:
            return super().save_m2m()
        except AttributeError:
            return None

    def clean(self):
        return super().clean()


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    form = VideoAdminForm
    list_display = (
        "title",
        "get_thumbnail",
        "uploaded_by",
        "created_at",
        "get_human_duration",
        "get_hls_progress",
    )
    list_filter = ("uploaded_by", "created_at")
    search_fields = ("title", "description", "uploaded_by__username")
    readonly_fields = (
        "get_thumbnail",
        "get_human_duration",
        "get_hls_progress_field",
        "get_hls_status_field",
        "get_human_filesize_field",
        "chunk_file_name_filed",
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
                    "chunk_file_name_filed",
                    "thumbnail",
                    "get_thumbnail",
                ),
            },
        ),
        (
            _("Статистика"),
            {
                "fields": (
                    "get_human_duration",
                    "get_human_filesize_field",
                    "created_at",
                    "get_hls_progress_field",
                    "get_hls_status_field",
                ),
            },
        ),
    )

    class Media:
        js = ("admin/js/hls_progress.js",)
        css = {
            "all": ("admin/css/hls_progress.css",),
        }

    def get_hls_progress(self, obj):
        # мини-полоска в списке
        return format_html(
            '<div class="hls-mini-bar" data-video-id="{}">'
            '  <div class="hls-mini-fill" style="width: {}%;">{}</div>'
            '  <div class="hls-mini-status">{}</div>'
            '  <div class="hls-mini-filesize">{}</div>'
            "</div>",
            obj.pk,
            obj.hls_progress or 0,
            f"{obj.hls_progress or 0}%",
            obj.hls_status or "—",
            self._get_human_filesize_value(obj),
        )

    get_hls_progress.short_description = "HLS"

    def _get_human_filesize_value(self, obj):
        """Внутренний метод для получения размера файла в читаемом формате"""
        size = obj.file_size
        if size is None:
            return _("неизвестно")

        units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
        for unit in units:
            if size < 1024.0:
                return f"{size:.1f} {unit}"

            size /= 1024.0

        return f"{size:.1f} ПБ"

    # полноразмерное поле на форме для прогресса
    def get_hls_progress_field(self, obj):
        if not obj.pk:
            return "No HLS info yet."
        # Блок будет обновляться JS через polling
        return format_html(
            """
            <div id="hls-progress-root" data-video-id="{vid}">
              <div class="hls-card">
                <div class="hls-header">
                  <strong>HLS processing</strong>
                  <span id="hls-status">{status}</span>
                </div>
                <div class="hls-bar-outer">
                  <div id="hls-bar" class="hls-bar-fill"\
                      style="width:{percent}%">
                    <span id="hls-percent-text">{percent}%</span>
                  </div>
                </div>
                <div class="hls-log" id="hls-log">{log}</div>
              </div>
            </div>
            """,
            vid=obj.pk,
            percent=obj.hls_progress or 0,
            status=obj.hls_status or "—",
            log=(obj.hls_log or "")[:2000],
        )

    get_hls_progress_field.short_description = "HLS progress"

    # отдельное поле для статуса HLS
    def get_hls_status_field(self, obj):
        if not obj.pk:
            return "—"

        return format_html(
            '<div id="hls-status-field" data-video-id="{}"\
                class="hls-status-container">'
            '  <span class="hls-status-badge hls-status-{}">{}</span>'
            "</div>",
            obj.pk,
            (obj.hls_status or "unknown").lower().replace(" ", "-"),
            obj.hls_status or "—",
        )

    get_hls_status_field.short_description = "HLS Status"

    # отдельное поле для размера файла
    def get_human_filesize_field(self, obj):
        if not obj.pk:
            return "—"

        return format_html(
            '<div id="hls-filesize-field" data-video-id="{}"\
                class="hls-filesize-container">'
            '  <span class="hls-filesize-value">{}</span>'
            "</div>",
            obj.pk,
            self._get_human_filesize_value(obj),
        )

    get_human_filesize_field.short_description = "Размер файла"

    # добавим view для ajax polling
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:object_id>/hls_progress/",
                self.admin_site.admin_view(self.hls_progress_view),
                name="video_hls_progress",
            ),
        ]
        return custom + urls

    def hls_progress_view(self, request, object_id, *args, **kwargs):
        try:
            obj = Video.objects.get(pk=object_id)
        except Video.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)

        # You may restrict to GET only
        data = {
            "progress": obj.hls_progress,
            "status": obj.hls_status,
            "log_tail": (obj.hls_log or "")[-2000:],
            "manifest": obj.hls_manifest.url if obj.hls_manifest else None,
            "filesize": self._get_human_filesize_value(obj),
        }
        return JsonResponse(data)

    def get_thumbnail(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" width="100" height="auto" />',
                obj.thumbnail.url,
            )

        return _("Нет превью")

    get_thumbnail.short_description = _("предпросмотр превью")

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
        return self._get_human_filesize_value(obj)

    get_human_filesize.short_description = _("Размер файла")

    def chunk_file_name_filed(self, obj):
        chunk_file = obj.file
        if chunk_file:
            return format_html(f"<p>{chunk_file}</p>")

        return format_html("<p>Файл ещё не загужен</p>")

    chunk_file_name_filed.short_description = _("имя чанка файла")


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
