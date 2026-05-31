import asyncio
import json
import re
import time
from urllib.parse import parse_qs, urlparse

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import (
    HttpResponseNotFound,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
)
import httpx
import yt_dlp

from rooms.forms import JoinPrivateRoomForm, RoomCreateForm, RoomUpdateForm
from rooms.models import WatchParty

__all__ = ()


class RoomsView(ListView):
    model = WatchParty
    context_object_name = "rooms"
    template_name = "rooms/room_list.html"
    paginate_by = 10

    def get_queryset(self):
        return WatchParty.objects.filter(is_private=False).order_by(
            "-created_at",
        )


class RoomDetailView(DetailView):
    model = WatchParty
    context_object_name = "room"
    template_name = "rooms/room_detail.html"

    def get_queryset(self):
        return WatchParty.objects.prefetch_related(
            "participants",
            "video",
            "host",
        )

    def get(self, request, *args, **kwargs):
        room = self.get_object()

        # Проверка доступа к приватной комнате
        if room.is_private and request.user.is_authenticated:
            # Организатор и участники имеют доступ
            if (
                request.user != room.host
                and request.user not in room.participants.all()
            ):
                # Проверяем, был ли предоставлен код доступа в сессии
                session_key = f"room_access_{room.pk}"
                if not request.session.get(session_key):
                    messages.error(
                        request,
                        "Эта комната приватная. Используйте код доступа дл\
                            я входа.",
                    )
                    return redirect("rooms:join_private")

        return super().get(request, *args, **kwargs)


class JoinRoomView(LoginRequiredMixin, View):
    def post(self, request, pk):
        room = get_object_or_404(WatchParty, pk=pk)

        # Проверка приватной комнаты
        if room.is_private:
            session_key = f"room_access_{room.pk}"
            if (
                not request.session.get(session_key)
                and request.user != room.host
            ):
                messages.error(
                    request,
                    "Для доступа к приватной комнате используйте код доступа.",
                )
                return redirect("rooms:join_private")

        if room.participants.count() >= room.limit_participants:
            messages.error(request, "Лимит участников достигнут.")
        elif request.user in room.participants.all():
            messages.info(request, "Вы уже участник этой комнаты.")
        else:
            room.participants.add(request.user)
            messages.success(
                request,
                f"Вы присоединились к комнате «{room.name}».",
            )

            # Отправляем системное сообщение и список участников
            channel_layer = get_channel_layer()
            participants = list(
                room.participants.values_list("username", flat=True),
            )
            async_to_sync(channel_layer.group_send)(
                f"watchparty_{room.pk}",
                {
                    "type": "broadcast",
                    "text": json.dumps(
                        {
                            "type": "message",
                            "message": f"{request.user.username} \
                                присоединился к комнате",
                            "system": True,
                            "username": request.user.username,
                        },
                    ),
                },
            )
            async_to_sync(channel_layer.group_send)(
                f"watchparty_{room.pk}",
                {
                    "type": "broadcast",
                    "text": json.dumps(
                        {
                            "type": "participants",
                            "participants": participants,
                        },
                    ),
                },
            )

        return redirect(reverse("rooms:detail", kwargs={"pk": room.pk}))


class LeaveRoomView(LoginRequiredMixin, View):
    def post(self, request, pk):
        room = get_object_or_404(WatchParty, pk=pk)
        room.participants.remove(request.user)
        messages.success(request, f"Вы покинули комнату «{room.name}».")

        channel_layer = get_channel_layer()
        participants = list(
            room.participants.values_list("username", flat=True),
        )
        async_to_sync(channel_layer.group_send)(
            f"watchparty_{room.pk}",
            {
                "type": "broadcast",
                "text": json.dumps(
                    {
                        "type": "message",
                        "message": f"{request.user.username}\
                            покинул(а) комнату",
                        "system": True,
                        "username": request.user.username,
                    },
                ),
            },
        )
        async_to_sync(channel_layer.group_send)(
            f"watchparty_{room.pk}",
            {
                "type": "broadcast",
                "text": json.dumps(
                    {
                        "type": "participants",
                        "participants": participants,
                    },
                ),
            },
        )
        return redirect(reverse("rooms:list"))


class RoomCreateView(LoginRequiredMixin, CreateView):
    """Представление для создания новой комнаты"""

    model = WatchParty
    form_class = RoomCreateForm
    template_name = "rooms/room_create.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        # Устанавливаем текущего пользователя как организатора
        form.instance.host = self.request.user
        response = super().form_valid(form)

        # Автоматически добавляем организатора в участники
        self.object.participants.add(self.request.user)

        # Показываем сообщение с кодом доступа, если комната приватная
        if self.object.is_private and self.object.access_code:
            messages.success(
                self.request,
                f'Комната "{self.object.name}" создана! Код доступа: \
                    {self.object.access_code}. '
                "Сохраните его для приглашения друзей.",
            )
        else:
            messages.success(
                self.request,
                f'Комната "{self.object.name}" успешно создана!',
            )

        return response  # noqa

    def get_success_url(self):
        return reverse("rooms:detail", kwargs={"pk": self.object.pk})


class JoinPrivateRoomView(LoginRequiredMixin, FormView):
    """Представление для присоединения к приватной комнате по коду"""

    form_class = JoinPrivateRoomForm
    template_name = "rooms/join_private.html"

    def form_valid(self, form):
        code = form.cleaned_data["access_code"]

        try:
            room = WatchParty.objects.get(access_code=code, is_private=True)

            # Сохраняем доступ в сессии
            session_key = f"room_access_{room.pk}"
            self.request.session[session_key] = True

            # Проверяем, не является ли пользователь уже участником
            if self.request.user in room.participants.all():
                messages.info(
                    self.request,
                    f'Вы уже участник комнаты "{room.name}".',
                )
                return redirect("rooms:detail", pk=room.pk)

            # Проверяем лимит участников
            if room.participants.count() >= room.limit_participants:
                messages.error(
                    self.request,
                    "Лимит участников в этой комнате достигнут.",
                )
                return self.form_invalid(form)

            # Добавляем пользователя в участники
            room.participants.add(self.request.user)

            messages.success(
                self.request,
                f'Вы успешно присоединились к приватной комн\
                    ате "{room.name}"!',
            )

            # Отправляем системное сообщение
            channel_layer = get_channel_layer()
            participants = list(
                room.participants.values_list("username", flat=True),
            )
            async_to_sync(channel_layer.group_send)(
                f"watchparty_{room.pk}",
                {
                    "type": "broadcast",
                    "text": json.dumps(
                        {
                            "type": "message",
                            "message": f"{self.request.user.username} \
                                присоединился к комнате",
                            "system": True,
                            "username": self.request.user.username,
                        },
                    ),
                },
            )
            async_to_sync(channel_layer.group_send)(
                f"watchparty_{room.pk}",
                {
                    "type": "broadcast",
                    "text": json.dumps(
                        {
                            "type": "participants",
                            "participants": participants,
                        },
                    ),
                },
            )

            return redirect("rooms:detail", pk=room.pk)

        except WatchParty.DoesNotExist:
            messages.error(self.request, "Комната с таким кодом не найдена.")
            return self.form_invalid(form)


class RoomUpdateView(LoginRequiredMixin, UpdateView):
    """Представление для редактирования комнаты"""

    model = WatchParty
    form_class = RoomUpdateForm
    template_name = "rooms/room_update.html"
    context_object_name = "room"

    def get_queryset(self):
        # Только организатор может редактировать комнату
        return WatchParty.objects.filter(host=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)

        # Показываем сообщение об успехе
        if self.object.is_private and self.object.access_code:
            if form.cleaned_data.get("generate_code"):
                messages.success(
                    self.request,
                    f"Комната обновлена! Новый код доступ\
                        а: {self.object.access_code}",
                )
            else:
                messages.success(self.request, "Комната успешно обновлена!")
        else:
            messages.success(self.request, "Комната успешно обновлена!")

        return response  # noqa

    def get_success_url(self):
        return reverse("rooms:detail", kwargs={"pk": self.object.pk})


class RoomDeleteView(LoginRequiredMixin, DeleteView):
    """Представление для удаления комнаты"""

    model = WatchParty
    template_name = "rooms/room_delete.html"
    context_object_name = "room"
    success_url = reverse_lazy("rooms:manage")

    def get_queryset(self):
        # Только организатор может удалить комнату
        return WatchParty.objects.filter(host=self.request.user)

    def delete(self, request, *args, **kwargs):
        room = self.get_object()
        messages.success(request, f'Комната "{room.name}" успешно удалена.')
        return super().delete(request, *args, **kwargs)


class RoomManageView(LoginRequiredMixin, ListView):
    """Представление для управления комнатами пользователя"""

    model = WatchParty
    template_name = "rooms/room_manage.html"
    context_object_name = "hosted_rooms"

    def get_queryset(self):
        # Комнаты, которые создал пользователь
        return WatchParty.objects.filter(host=self.request.user).order_by(
            "-created_at",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Комнаты, в которых участвует пользователь (но не организатор)
        context["joined_rooms"] = (
            WatchParty.objects.filter(participants=self.request.user)
            .exclude(host=self.request.user)
            .order_by("-created_at")
        )
        return context


# ── Helpers ──────────────────────────────────────────────────────────────────


def extract_gdrive_file_id(url: str) -> str | None:
    """Extract file ID from various Google Drive URL formats."""
    # /file/d/<id>/view
    m = re.search(r"/file/d/([-\w]+)", url)
    if m:
        return m.group(1)
    # id=<id>
    m = re.search(r"[?&]id=([-\w]+)", url)
    if m:
        return m.group(1)
    # uc?export=download&id=<id> or u/0/uc?id=<id>
    m = re.search(r"[-\w]{25,}", url)
    if m:
        return m.group(0)

    return None


def _is_video_response(upstream) -> bool:
    """Return True when the upstream response looks like video bytes."""
    ct = (upstream.headers.get("Content-Type") or "").lower()
    return "text/html" not in ct


def _extract_url_expiry(url: str) -> int | None:
    """Extract Unix-timestamp expiry from a YouTube signed stream URL."""
    if not url:
        return None

    try:
        params = parse_qs(urlparse(url).query)
        expire = params.get("expire", [None])[0]
        if expire:
            return int(expire)
    except Exception:
        pass

    return None


def _pick_cache_timeout(
    expires_at: int | None,
    default_seconds: int = 1800,
) -> int:
    """Safe cache TTL that never serves a URL past its expiry."""
    if not expires_at:
        return default_seconds

    seconds_until_expiry = expires_at - int(time.time())
    safe_ttl = seconds_until_expiry - 90
    return max(60, min(default_seconds, safe_ttl))


# ── ExternalStreamView ───────────────────────────────────────────────────────


class ExternalStreamView(LoginRequiredMixin, View):
    """
    Return a single direct stream URL for external videos.

    For YouTube we request **combined** formats (audio+video in one
    stream) so the frontend never needs a fragile separate audio element.
    For Google Drive we point the frontend to our proxy view which streams
    the file safely through Django with proper Range-header support.

    GET /rooms/<pk>/stream/  →  { "url": "...", "expires_at": <unix|None> }
    GET /rooms/<pk>/stream/?refresh=1  →  bypasses cache
    """

    def get(self, request, pk):
        room = get_object_or_404(WatchParty, pk=pk)
        force_refresh = request.GET.get("refresh") == "1"

        if not room.external_url:
            return JsonResponse(
                {"error": "No external URL configured for this room"},
                status=400,
            )

        # ── Google Drive: stream through Django proxy ───────────────────────
        # Proxying through Django guarantees a clean same-origin stream with
        # proper Range-header support and strips Content-Disposition
        # that Google's CDN sends (which would otherwise trigger a download).
        if "drive.google.com" in room.external_url.lower():
            file_id = extract_gdrive_file_id(room.external_url)
            if not file_id:
                return JsonResponse(
                    {"error": "Could not extract Google Drive file ID"},
                    status=400,
                )

            proxy_url = reverse(
                "rooms:gdrive_proxy",
                kwargs={"pk": room.pk},
            )
            return JsonResponse({"url": proxy_url})

        # ── YouTube (or any yt-dlp source): quality switching ──────────────
        #   No quality param → return best COMBINED (always works) + list of
        #   available video-only formats for the quality selector.
        #
        #   ?quality=<height> → return DASH video+audio URLs at that height
        #   (h264 mp4 preferred, fall back to av01 → combined).
        #
        quality_param = request.GET.get("quality")

        # ── quality switch ─────────────────────────────────────────────────
        if quality_param:
            try:
                target_height = int(quality_param)
                # If 360p is requested, just re-extract the combined URL
                if target_height <= 360:
                    ydl_opts = {
                        "quiet": True,
                        "nocheckcertificate": True,
                        "format": "best[ext=mp4]",
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        qinfo = ydl.extract_info(
                            room.external_url,
                            download=False,
                        )
                        qurl = qinfo.get("url")
                        if not qurl:
                            return JsonResponse(
                                {"error": "Could not fetch stream URL"},
                                status=502,
                            )

                        return JsonResponse(
                            {
                                "url": qurl,
                                "audio_url": None,
                                "expires_at": _extract_url_expiry(qurl),
                            },
                        )

                # 480p+ → DASH: bestvideo (h264 mp4) + bestaudio (aac m4a)
                fmt = (
                    f"bestvideo[height<={target_height}]"
                    f"[ext=mp4][vcodec^=avc1]"
                    f"+bestaudio[ext=m4a]"
                    f"/bestvideo[height<={target_height}]"
                    f"[ext=mp4]+bestaudio[ext=m4a]"
                    f"/best[ext=mp4]"
                )
                ydl_opts = {
                    "quiet": True,
                    "nocheckcertificate": True,
                    "format": fmt,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    qinfo = ydl.extract_info(
                        room.external_url,
                        download=False,
                    )
                    req = qinfo.get("requested_formats") or []
                    video_url = next(
                        (
                            f["url"]
                            for f in req
                            if (f.get("vcodec") or "none").lower() != "none"
                        ),
                        None,
                    )
                    audio_url = next(
                        (
                            f["url"]
                            for f in req
                            if (f.get("acodec") or "none").lower() != "none"
                        ),
                        None,
                    )
                    # Fallback: combined (all-in-one) URL
                    if not video_url:
                        video_url = qinfo.get("url")
                        audio_url = None

                    if not video_url:
                        return JsonResponse(
                            {"error": "Could not fetch stream URL"},
                            status=502,
                        )

                    return JsonResponse(
                        {
                            "url": video_url,
                            "audio_url": audio_url,
                            "expires_at": _extract_url_expiry(video_url),
                        },
                    )
            except Exception as e:
                return JsonResponse({"error": str(e)}, status=500)

        # ── initial request (no quality param) ──────────────────────────────
        cache_key = f"room_external_url_{room.pk}"
        cache.delete(f"room_external_multi_{room.pk}")
        cached_data = None if force_refresh else cache.get(cache_key)

        if not cached_data:
            try:
                ydl_opts = {
                    "quiet": True,
                    "nocheckcertificate": True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(
                        room.external_url,
                        download=False,
                    )

                    if not room.external_title:
                        room.external_title = info.get("title", "")
                        room.save(update_fields=["external_title"])

                    # Build quality list from video-only mp4 formats.
                    # (Default stream is best combined — 360p — but users
                    # get full vertical resolution via DASH below.)
                    seen_heights = set()
                    qualities = []
                    for f in info.get("formats") or []:
                        vc = (f.get("vcodec") or "none").lower()
                        ac = (f.get("acodec") or "none").lower()
                        h = f.get("height") or 0
                        ext = (f.get("ext") or "").lower()
                        if (
                            vc != "none"
                            and ac == "none"
                            and h > 0
                            and ext == "mp4"
                        ):
                            if h not in seen_heights:
                                seen_heights.add(h)
                                qualities.append(
                                    {
                                        "label": f"{h}p",
                                        "height": h,
                                    },
                                )

                    qualities.sort(key=lambda x: x["height"], reverse=True)

                    # Default stream: best combined mp4 (always 360p)
                    ydl_default = {
                        "quiet": True,
                        "nocheckcertificate": True,
                        "format": "best[ext=mp4]",
                    }
                    with yt_dlp.YoutubeDL(ydl_default) as ydl2:
                        default_info = ydl2.extract_info(
                            room.external_url,
                            download=False,
                        )
                        stream_url = default_info.get("url")

                    if not stream_url:
                        return JsonResponse(
                            {"error": "Could not extract stream URL"},
                            status=500,
                        )

                    expires_at = _extract_url_expiry(stream_url)
                    cached_data = {
                        "url": stream_url,
                        "expires_at": expires_at,
                        "qualities": qualities,
                        "default_height": 360,
                    }
                    cache_timeout = _pick_cache_timeout(
                        expires_at,
                        default_seconds=60 * 30,
                    )
                    cache.set(cache_key, cached_data, timeout=cache_timeout)

            except Exception as e:
                return JsonResponse({"error": str(e)}, status=500)

        return JsonResponse(cached_data)


# ── GoogleDriveProxyView ─────────────────────────────────────────────────────


BUFFER_SIZE = 65536


async def _astream_from_url(request, url, file_id=None):
    req_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if range_hdr := request.META.get("HTTP_RANGE"):
        req_headers["Range"] = range_hdr

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, read=30.0),
    )
    try:
        upstream = await client.get(url, headers=req_headers)
    except Exception:
        await client.aclose()
        return HttpResponseNotFound("Upstream unreachable")

    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        return HttpResponseNotFound("Upstream error")

    if file_id and not _is_video_response(upstream):
        await upstream.aclose()
        await client.aclose()
        return await _astream_via_confirm_flow(request, file_id)

    return _abuild_response(upstream, client)


async def _astream_via_confirm_flow(request, file_id):
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, read=30.0),
    )
    try:
        base = f"https://docs.google.com/uc?export=download&id={file_id}"
        try:
            r1 = await client.get(base, follow_redirects=False)
        except Exception:
            await client.aclose()
            return HttpResponseNotFound("Google Drive unreachable")

        token = None
        for k, v in r1.cookies.items():
            if k.startswith("download_warning"):
                token = v
                break

        if not token:
            m = re.search(r"confirm=([\w-]+)", r1.text)
            if m:
                token = m.group(1)

        if not token:
            m = re.search(
                r'name="confirm"\s+value="([\w-]+)"',
                r1.text,
            )
            if m:
                token = m.group(1)

        confirm_url = f"{base}&confirm={token}" if token else base

        req_headers = {}
        if range_hdr := request.META.get("HTTP_RANGE"):
            req_headers["Range"] = range_hdr

        try:
            upstream = await client.get(
                confirm_url,
                headers=req_headers,
                follow_redirects=True,
            )
        except Exception:
            await client.aclose()
            return HttpResponseNotFound("Google Drive confirm failed")

        if upstream.status_code >= 400:
            await upstream.aclose()
            await client.aclose()
            return HttpResponseNotFound("Google Drive error")

        if not _is_video_response(upstream):
            await upstream.aclose()
            await client.aclose()
            return HttpResponseNotFound(
                "Google Drive returned non-video response",
            )

        return _abuild_response(upstream, client)
    except Exception:
        await client.aclose()
        raise


def _abuild_response(upstream, client):
    async def chunk_iter():
        try:
            async for chunk in upstream.aiter_bytes():
                if chunk:
                    yield chunk
        except GeneratorExit:
            raise
        finally:
            try:
                await asyncio.wait_for(upstream.aclose(), timeout=2)
            except Exception:
                pass

            try:
                await asyncio.wait_for(client.aclose(), timeout=2)
            except Exception:
                pass

    resp = StreamingHttpResponse(
        chunk_iter(),
        status=upstream.status_code,
        content_type=upstream.headers.get(
            "Content-Type",
            "video/mp4",
        ),
    )
    for hdr in (
        "Content-Range",
        "Accept-Ranges",
        "Content-Length",
    ):
        if hdr in upstream.headers:
            resp[hdr] = upstream.headers[hdr]

    if "Content-Disposition" in resp:
        del resp["Content-Disposition"]

    return resp


@sync_to_async
def _get_room_or_404(pk):
    return get_object_or_404(WatchParty, pk=pk)


async def google_drive_proxy_view(request, pk):
    """
    Stream a Google Drive video file through Django so the <video> element
    can read it without CORS / cookie issues.

    Handles:
    - Direct CDN URLs (googleusercontent.com)
    - Google Drive confirm-token flow (virus-scan page → CDN redirect)
    - HTTP Range headers for seeking
    """
    # Force user loading in a thread before accessing request.user
    # (which is a SimpleLazyObject that triggers a sync DB query).
    is_authenticated = await sync_to_async(
        lambda: request.user.is_authenticated,
        thread_sensitive=True,
    )()
    if not is_authenticated:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.path)

    room = await _get_room_or_404(pk)
    if "drive.google.com" not in (room.external_url or "").lower():
        return HttpResponseNotFound("Not a Google Drive URL")

    file_id = extract_gdrive_file_id(room.external_url)
    if not file_id:
        return HttpResponseNotFound("Could not extract file ID")

    cdn_url = (
        f"https://drive.usercontent.google.com/download"
        f"?id={file_id}&export=download&confirm=t"
    )
    return await _astream_from_url(request, cdn_url, file_id)
