import json
from pathlib import Path

from chunked_upload.views import ChunkedUploadCompleteView, ChunkedUploadView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
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
            raw_filename = (
                getattr(chunked_upload, "filename", None) or file_field.name
            )
            filename = Path(raw_filename).name if raw_filename else "unknown"

            try:
                validate_video_extension(filename)
                if hasattr(file_field, "size"):
                    validate_file_size(file_field.size)
            except ValueError as e:
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
        if file_field and hasattr(file_field, "size"):
            video.file_size = file_field.size

        # Добавляем превью если есть
        if req and req.FILES.get("thumbnail"):
            video.thumbnail = req.FILES["thumbnail"]

        video.save()

        # Обработка плейлиста
        playlist_id = req.POST.get("playlist_id") if req is not None else None
        playlist_title = (
            req.POST.get("playlist_title") if req is not None else None
        )
        season_number = req.POST.get("season_number", "1")
        episode_number = req.POST.get("episode_number", "1")
        order = req.POST.get("order", "0")

        playlist_data = None

        # Если указан существующий плейлист
        if playlist_id:
            try:
                playlist = Playlist.objects.get(pk=playlist_id)

                # Проверка владельца плейлиста
                check_user_owns_playlist(req.user, playlist)

                # Если order не передан, определяем его автоматически
                if not order or order == "0":
                    last_item = (
                        PlaylistItem.objects.filter(playlist=playlist)
                        .order_by("-order")
                        .first()
                    )
                    order = (last_item.order + 1) if last_item else 1

                # Проверяем, нет ли уже такой комбинации сезон/серия
                existing_item = PlaylistItem.objects.filter(
                    playlist=playlist,
                    season_number=int(season_number),
                    episode_number=int(episode_number),
                ).first()

                if existing_item:
                    last_episode = (
                        PlaylistItem.objects.filter(
                            playlist=playlist,
                            season_number=int(season_number),
                        )
                        .order_by("-episode_number")
                        .first()
                    )

                    if last_episode:
                        episode_number = str(last_episode.episode_number + 1)

                PlaylistItem.objects.create(
                    playlist=playlist,
                    video=video,
                    season_number=int(season_number),
                    episode_number=int(episode_number),
                    order=int(order),
                )

                playlist_data = {
                    "id": playlist.pk,
                    "title": playlist.title,
                }
            except (Playlist.DoesNotExist, ValueError):
                pass

        # Если нужно создать новый плейлист
        elif playlist_title:
            playlist = Playlist(
                title=playlist_title,
                description=req.POST.get("playlist_description", ""),
                created_by=req.user,
            )

            # Добавляем обложку плейлиста, если она передана
            if req and req.FILES.get("playlist_cover"):
                playlist.cover_image = req.FILES["playlist_cover"]

            playlist.save()

            # Если order не передан, используем 1 для первого элемента
            if not order or order == "0":
                order = "1"

            PlaylistItem.objects.create(
                playlist=playlist,
                video=video,
                season_number=int(season_number),
                episode_number=int(episode_number),
                order=int(order),
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


class PlaylistVideosView(LoginRequiredMixin, View):
    """
    API для получения видео из плейлиста
    """

    def get(self, request, playlist_id):
        try:
            playlist = Playlist.objects.get(pk=playlist_id)

            # Проверка прав доступа
            check_user_owns_playlist(request.user, playlist)

            # Получаем все видео в плейлисте
            items = (
                PlaylistItem.objects.filter(playlist=playlist)
                .select_related("video")
                .order_by("order")
            )

            videos = []
            for item in items:
                videos.append(
                    {
                        "id": item.id,
                        "video_id": item.video.id,
                        "title": item.video.title,
                        "description": item.video.description,
                        "thumbnail_url": (
                            item.video.thumbnail.url
                            if item.video.thumbnail
                            else None
                        ),
                        "season_number": item.season_number,
                        "episode_number": item.episode_number,
                        "order": item.order,
                        "duration": item.video.duration,
                        "file_size": item.video.file_size,
                        "created_at": (
                            item.video.created_at.isoformat()
                            if item.video.created_at
                            else None
                        ),
                    },
                )

            return JsonResponse(
                {
                    "success": True,
                    "playlist": {
                        "id": playlist.id,
                        "title": playlist.title,
                        "description": playlist.description,
                    },
                    "videos": videos,
                },
            )

        except Playlist.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Плейлист не найден"},
                status=404,
            )
        except PermissionDenied as e:
            return JsonResponse(
                {"success": False, "error": str(e)},
                status=403,
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Ошибка при получении видео: {str(e)}",
                },
                status=500,
            )


class UpdateVideoMetadataView(LoginRequiredMixin, View):
    """
    API для обновления метаданных видео (название, описание, превью)
    """

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, video_id):
        try:
            video = Video.objects.get(pk=video_id)

            # Проверка прав доступа
            if video.uploaded_by != request.user:
                raise PermissionDenied(
                    "У вас нет прав для редактирования этого видео",
                )

            # Если это multipart/form-data (загрузка превью)
            if request.FILES.get("thumbnail"):
                video.thumbnail = request.FILES["thumbnail"]
                video.save(update_fields=["thumbnail"])

                return JsonResponse(
                    {"success": True, "message": "Превью обновлено"},
                )

            # Если это JSON (обновление текстовых полей)
            data = json.loads(request.body)

            updated_fields = []
            if "title" in data:
                video.title = data["title"]
                updated_fields.append("title")

            if "description" in data:
                video.description = data["description"]
                updated_fields.append("description")

            if updated_fields:
                video.save(update_fields=updated_fields)

            return JsonResponse(
                {
                    "success": True,
                    "message": "Метаданные обновлены",
                    "video": {
                        "id": video.id,
                        "title": video.title,
                        "description": video.description,
                    },
                },
            )

        except Video.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Видео не найдено"},
                status=404,
            )
        except PermissionDenied as e:
            return JsonResponse(
                {"success": False, "error": str(e)},
                status=403,
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Ошибка при обновлении: {str(e)}",
                },
                status=500,
            )


class UpdatePlaylistOrderView(LoginRequiredMixin, View):
    """
    API для обновления порядка видео в плейлисте
    """

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        try:
            data = json.loads(request.body)
            playlist_id = data.get("playlist_id")
            items = data.get(
                "items",
                [],
            )  # [{id: item_id, order: new_order, season: N, episode: N}, ...]

            if not playlist_id or not items:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Не указан плейлист или список элементов",
                    },
                    status=400,
                )

            playlist = Playlist.objects.get(pk=playlist_id)

            # Проверка прав доступа
            check_user_owns_playlist(request.user, playlist)

            # Обновляем порядок в транзакции
            with transaction.atomic():
                for item_data in items:
                    item = PlaylistItem.objects.get(
                        pk=item_data["id"],
                        playlist=playlist,
                    )
                    item.order = item_data["order"]
                    if "season_number" in item_data:
                        item.season_number = item_data["season_number"]

                    if "episode_number" in item_data:
                        item.episode_number = item_data["episode_number"]

                    item.save()

            return JsonResponse(
                {"success": True, "message": "Порядок успешно обновлен"},
            )

        except Playlist.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Плейлист не найден"},
                status=404,
            )
        except PlaylistItem.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Элемент плейлиста не найден"},
                status=404,
            )
        except PermissionDenied as e:
            return JsonResponse(
                {"success": False, "error": str(e)},
                status=403,
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Ошибка при обновлении порядка: {str(e)}",
                },
                status=500,
            )
