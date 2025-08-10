import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache

from rooms.models import ChatMessage, WatchParty
from upload.models import Video

__all__ = ("WatchPartySyncConsumer",)


class WatchPartySyncConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.party_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.group_name = f"watchparty_{self.party_id}"
        self.user = self.scope["user"]

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # история чата + участники (как было)
        history = await self.get_last_messages(limit=50)
        await self.send(
            text_data=json.dumps({"type": "history", "messages": history}),
        )
        participants = await self.get_participants()
        await self.send(
            text_data=json.dumps(
                {"type": "participants", "participants": participants},
            ),
        )
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "participants_update", "participants": participants},
        )

        # Отправляем текущее состояние плеера (если есть) — NEW
        state = await self.get_watchparty_state()
        if state:
            await self.send(
                text_data=json.dumps({"type": "player_state", "state": state}),
            )

    async def disconnect(self, close_code):
        participants = await self.get_participants()
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "participants_update", "participants": participants},
        )
        await self.channel_layer.group_discard(
            self.group_name, self.channel_name,
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.sync_broadcast(text_data)
            return

        msg_type = data.get("type")

        if msg_type == "chat":
            message = data.get("message", "").strip()
            if message:
                username = (
                    self.user.username
                    if self.user.is_authenticated
                    else "Гость"
                )
                await self.save_message(
                    message, username, data.get("system", False),
                )
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "chat_message",
                        "message": message,
                        "username": username,
                        "system": data.get("system", False),
                    },
                )

            return

        if msg_type == "participants_update":
            participants = await self.get_participants()
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "participants_update",
                    "participants": participants,
                },
            )
            return

        if msg_type == "playlist_select":
            item = data.get("item", {})
            video_id = item.get("video_id")
            # Сохраняем текущий video в WatchParty (опционально)
            if video_id:
                await self.save_watchparty_video(video_id)

            await self.set_watchparty_state(
                time=0.0,
                ts=data.get("ts", None)
                or int(__import__("time").time() * 1000),
                is_playing=True,
                video_id=video_id,
                hls_url=item.get("hls_url"),
            )

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "playlist_change",
                    "item": item,
                    "initiator": (
                        self.user.username
                        if self.user.is_authenticated
                        else "Гость"
                    ),
                    "ts": data.get("ts", None),
                },
            )
            return

        if msg_type in ("play", "pause", "seek", "keyframe"):
            try:
                time_val = float(data.get("time", 0.0))
            except (TypeError, ValueError):
                time_val = 0.0

            is_playing = True if msg_type in ("play", "keyframe") else False
            ts = data.get("ts", None) or int(__import__("time").time() * 1000)

            room = await self.get_room_once()
            hls = None
            vid = None
            if room and getattr(room, "video", None):
                try:
                    hls = room.video.hls_manifest.url
                    vid = room.video.id
                except Exception:
                    hls = None

            await self.set_watchparty_state(
                time=time_val,
                ts=ts,
                is_playing=is_playing,
                video_id=vid,
                hls_url=hls,
            )

            # Передаем остальным (старое поведение)
            await self.sync_broadcast(text_data)
            return

        # всё остальное — пасс
        await self.sync_broadcast(text_data)

    # ========== Group handlers ==========
    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "username": event["username"],
                    "message": event["message"],
                    "system": event.get("system", False),
                },
            ),
        )

    async def participants_update(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "participants",
                    "participants": event["participants"],
                    "count": len(event["participants"]),
                },
            ),
        )

    async def playlist_change(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "playlist_change",
                    "item": event.get("item", {}),
                    "initiator": event.get("initiator"),
                    "ts": event.get("ts"),
                },
            ),
        )

    async def broadcast(self, event):
        await self.send(text_data=event["text"])

    # ========== Helpers: DB / cache ==========
    @database_sync_to_async
    def get_participants(self):
        try:
            party = WatchParty.objects.get(id=self.party_id)
            return list(party.participants.values_list("username", flat=True))
        except WatchParty.DoesNotExist:
            return []

    @database_sync_to_async
    def get_last_messages(self, limit=50):
        messages = ChatMessage.objects.filter(room_id=self.party_id).order_by(
            "-created_at",
        )[:limit]
        return [
            {
                "username": m.user.username if m.user else "Система",
                "message": m.content,
                "system": m.is_system,
            }
            for m in reversed(messages)
        ]

    @database_sync_to_async
    def save_message(self, content, username=None, is_system=False):
        user = None
        if username and not is_system and self.user.is_authenticated:
            user = self.user

        room = WatchParty.objects.get(id=self.party_id)
        ChatMessage.objects.create(
            room=room, user=user, content=content, is_system=is_system,
        )

    @database_sync_to_async
    def save_watchparty_video(self, video_id):
        try:
            room = WatchParty.objects.get(id=self.party_id)
            v = Video.objects.get(id=video_id)
            room.video = v
            room.save()
            return True
        except Exception:
            return False

    @database_sync_to_async
    def get_room_once(self):
        try:
            return WatchParty.objects.select_related("video").get(
                id=self.party_id,
            )
        except WatchParty.DoesNotExist:
            return None

    # ---- cached state helpers (no DB migrations) ----
    @database_sync_to_async
    def set_watchparty_state(
        self, time, ts, is_playing, video_id=None, hls_url=None,
    ):
        key = f"watchparty_state_{self.party_id}"
        state = {
            "time": float(time or 0.0),
            "ts": (
                int(ts)
                if ts is not None
                else int(__import__("time").time() * 1000)
            ),
            "is_playing": bool(is_playing),
            "video_id": int(video_id) if video_id is not None else None,
            "hls_url": str(hls_url) if hls_url else None,
        }
        cache.set(
            key, state, None,
        )  # timeout=None -> persist until invalidated
        return True

    @database_sync_to_async
    def get_watchparty_state(self):
        key = f"watchparty_state_{self.party_id}"
        st = cache.get(key)
        if st:
            return st
        # fallback: try to fill from DB room.video
        try:
            room = WatchParty.objects.select_related("video").get(
                id=self.party_id,
            )
            if room.video and getattr(room.video, "hls_manifest", None):
                return {
                    "time": 0.0,
                    "ts": int(__import__("time").time() * 1000),
                    "is_playing": False,
                    "video_id": room.video.id,
                    "hls_url": room.video.hls_manifest.url,
                }
        except WatchParty.DoesNotExist:
            return None

        return None

    async def sync_broadcast(self, text_data):
        await self.channel_layer.group_send(
            self.group_name, {"type": "broadcast", "text": text_data},
        )
