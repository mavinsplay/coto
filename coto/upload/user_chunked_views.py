from pathlib import Path

from chunked_upload.views import ChunkedUploadCompleteView, ChunkedUploadView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from upload.models import Playlist, PlaylistItem, Video
from upload.permissions import (
    check_user_can_upload,
    check_user_owns_playlist,
    validate_file_size,
    validate_video_extension,
)


__all__ = [
    "UserChunkedUploadView",
    "UserChunkedUploadCompleteView",
    "UserUploadPageView",
]


@method_decorator(ensure_csrf_cookie, name="dispatch")
class UserChunkedUploadView(
    LoginRequiredMixin,
    ChunkedUploadView,
):
    """
    Chunked upload для обычных пользователей.
    Принимает чанки видеофайлов.
    """

    field_name = "file"
    
    def check_permissions(self, request):
        """Проверка прав доступа."""
        super().check_permissions(request)
        check_user_can_upload(request.user)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class UserChunkedUploadCompleteView(
    LoginRequiredMixin,
    ChunkedUploadCompleteView,
):
    """
    Завершение загрузки чанков и создание Video объекта.
    Может также создавать плейлист и добавлять видео в него.
    """

    def get_response_data(self, chunked_upload, request=None):
        req = request or getattr(self, "request", None)
        file_field = chunked_upload.file

        # Проверка прав доступа
        check_user_can_upload(req.user)

        # Валидация файла
        if file_field:
            # Получаем имя файла (может быть путём, берём только имя)
            raw_filename = getattr(chunked_upload, "filename", None) or file_field.name
            filename = Path(raw_filename).name if raw_filename else "unknown"
            
            print(f"[DEBUG] Validating file: raw='{raw_filename}', name='{filename}'")
            
            try:
                validate_video_extension(filename)
                if hasattr(file_field, 'size'):
                    validate_file_size(file_field.size)
            except ValueError as e:
                print(f"[ERROR] Validation failed: {e}")
                raise ValidationError(str(e))

        # Получаем данные из запроса
        title = (
            (req.POST.get("title") if req is not None else None)
            or getattr(chunked_upload, "filename", None)
            or (
                Path(file_field.name).name
                if file_field and file_field.name
                else "file"
            )
        )

        description = (
            req.POST.get("description", "") if req is not None else ""
        )

        # Создаем видео
        video = Video(
            title=title,
            description=description,
            file=file_field,
            uploaded_by=(req.user if req is not None else None),
        )
        
        # Получаем размер файла
        if file_field and hasattr(file_field, 'size'):
            video.file_size = file_field.size
            
        video.save()

        # Обработка плейлиста
        playlist_id = req.POST.get("playlist_id") if req is not None else None
        playlist_title = (
            req.POST.get("playlist_title") if req is not None else None
        )
        season_number = req.POST.get("season_number", "1")
        episode_number = req.POST.get("episode_number", "1")

        playlist_data = None

        # Если указан существующий плейлист
        if playlist_id:
            try:
                playlist = Playlist.objects.get(pk=playlist_id)
                
                # Проверка владельца плейлиста
                check_user_owns_playlist(req.user, playlist)
                
                # Определяем следующий номер серии
                last_item = (
                    PlaylistItem.objects.filter(
                        playlist=playlist,
                        season_number=season_number,
                    )
                    .order_by("-episode_number")
                    .first()
                )
                
                if last_item:
                    episode_number = last_item.episode_number + 1
                    
                PlaylistItem.objects.create(
                    playlist=playlist,
                    video=video,
                    season_number=int(season_number),
                    episode_number=int(episode_number),
                )
                
                playlist_data = {
                    "id": playlist.pk,
                    "title": playlist.title,
                }
            except (Playlist.DoesNotExist, ValueError):
                pass

        # Если нужно создать новый плейлист
        elif playlist_title:
            playlist = Playlist.objects.create(
                title=playlist_title,
                description=req.POST.get("playlist_description", ""),
                created_by=req.user,
            )
            
            PlaylistItem.objects.create(
                playlist=playlist,
                video=video,
                season_number=int(season_number),
                episode_number=int(episode_number),
            )
            
            playlist_data = {
                "id": playlist.pk,
                "title": playlist.title,
            }

        response_data = {
            "video_id": video.pk,
            "video_url": video.file.url if video.file else None,
            "title": video.title,
            "file_size": video.file_size,
        }
        
        if playlist_data:
            response_data["playlist"] = playlist_data

        return response_data


class UserUploadPageView(LoginRequiredMixin, TemplateView):
    """
    Страница загрузки видео для пользователей.
    """

    template_name = "upload/user_upload.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Получаем плейлисты пользователя
        context["user_playlists"] = Playlist.objects.filter(
            created_by=self.request.user,
        ).order_by("-created_at")
        return context
