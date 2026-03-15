import datetime
import json
import time as _time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache


__all__ = ("WatchPartySyncConsumer",)

# ─── Cache key helpers ───────────────────────────────────────────────────────


def _state_key(room_id):
    return f"watchparty_state_{room_id}"


def _online_key(room_id):
    return f"watchparty_online_{room_id}"


def _online_add(room_id, username):
    """Add username to the online set stored in cache."""
    key = _online_key(room_id)
    online = cache.get(key) or set()
    online.add(username)
    cache.set(key, online, None)


def _online_remove(room_id, username):
    """Remove username from the online set stored in cache."""
    key = _online_key(room_id)
    online = cache.get(key) or set()
    online.discard(username)
    cache.set(key, online, None)


def _online_set(room_id):
    return cache.get(_online_key(room_id)) or set()


# ─── Consumer ────────────────────────────────────────────────────────────────


class WatchPartySyncConsumer(AsyncWebsocketConsumer):

    # ──────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────

    async def connect(self):
        self.party_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.group_name = f"watchparty_{self.party_id}"
        self.user = self.scope["user"]

        # ❌ Block unauthenticated users completely
        if not self.user.is_authenticated:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Mark user online
        _online_add(self.party_id, self.user.username)

        # Send chat history
        history = await self.get_last_messages(limit=50)
        await self.send(
            text_data=json.dumps({"type": "history", "messages": history}),
        )

        # Send participants list (with status) to everyone
        participants = await self.get_participants_with_status()
        await self.send(
            text_data=json.dumps(
                {
                    "type": "participants",
                    "participants": participants,
                    "count": len(participants),
                },
            ),
        )
        # Broadcast updated status to rest of the room
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "participants_update", "participants": participants},
        )

        # Send current player state to the newly connected client
        state = await self.get_watchparty_state()
        if state:
            await self.send(
                text_data=json.dumps({"type": "player_state", "state": state}),
            )

    async def disconnect(self, close_code):
        if hasattr(self, "user") and self.user.is_authenticated:
            _online_remove(self.party_id, self.user.username)

        if hasattr(self, "group_name"):
            participants = await self.get_participants_with_status()
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "participants_update", "participants": participants},
            )
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.sync_broadcast(text_data)
            return

        msg_type = data.get("type")

        # ── Chat ──────────────────────────────────────────────────────────
        if msg_type == "chat":
            message = data.get("message", "").strip()
            if message:
                username = (
                    self.user.username
                    if self.user.is_authenticated
                    else "Гость"
                )
                timestamp = data.get("timestamp")
                if not timestamp:
                    timestamp = datetime.datetime.utcnow().isoformat() + "Z"

                await self.save_message(
                    message,
                    username,
                    data.get("system", False),
                )
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "chat_message",
                        "message": message,
                        "username": username,
                        "system": data.get("system", False),
                        "timestamp": timestamp,
                    },
                )

            return

        # ── Participants refresh ───────────────────────────────────────────
        if msg_type == "participants_update":
            participants = await self.get_participants_with_status()
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "participants_update",
                    "participants": participants,
                },
            )
            return

        # ── Request current player state (new client asking) ─────────────
        if msg_type == "request_state":
            state = await self.get_watchparty_state()
            if state:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "player_state",
                            "state": state,
                        },
                    ),
                )

            return

        # ── Playlist select ───────────────────────────────────────────────
        if msg_type == "playlist_select":
            item = data.get("item", {})
            video_id = item.get("video_id")
            if video_id:
                await self.save_watchparty_video(video_id)

            await self.set_watchparty_state(
                time=0.0,
                ts=data.get("ts") or int(_time.time() * 1000),
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
                    "ts": data.get("ts"),
                },
            )
            return

        # ── Playback commands ─────────────────────────────────────────────
        if msg_type in ("play", "pause", "seek", "keyframe"):
            try:
                time_val = float(data.get("time", 0.0))
            except (TypeError, ValueError):
                time_val = 0.0

            ts = data.get("ts") or int(_time.time() * 1000)

            # For keyframe: only update is_playing if currently playing
            # (don't override a pause with a keyframe)
            if msg_type == "keyframe":
                current_state = cache.get(_state_key(self.party_id))
                was_playing = (
                    current_state.get("is_playing", True)
                    if current_state
                    else True
                )
                is_playing = was_playing
                # Don't update state if time goes backward (stale packet)
                if current_state:
                    stored_time = current_state.get("time", 0.0)
                    # Only update if time advanced or big jump
                    if time_val < stored_time - 1.0:
                        await self.sync_broadcast(text_data)
                        return
            else:
                is_playing = msg_type in ("play",)

            # For pause, use the time from the message (accurate position)
            # For seek, same

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

            await self.sync_broadcast(text_data)
            return

        # ── Fallthrough ───────────────────────────────────────────────────
        await self.sync_broadcast(text_data)

    # ──────────────────────────────────────────────────────────────────────
    # Group event handlers
    # ──────────────────────────────────────────────────────────────────────

    async def chat_message(self, event):
        ts = event.get("timestamp")
        if not ts:
            ts = datetime.datetime.utcnow().isoformat() + "Z"

        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "username": event["username"],
                    "message": event["message"],
                    "system": event.get("system", False),
                    "timestamp": ts,
                },
            ),
        )

    async def participants_update(self, event):
        participants = event["participants"]
        await self.send(
            text_data=json.dumps(
                {
                    "type": "participants",
                    "participants": participants,
                    "count": len(participants),
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

    # ──────────────────────────────────────────────────────────────────────
    # DB / Cache helpers
    # ──────────────────────────────────────────────────────────────────────

    @database_sync_to_async
    def get_participants_with_status(self):
        """Return list of {username, online} dicts."""
        from rooms.models import WatchParty

        try:
            party = WatchParty.objects.get(id=self.party_id)
            db_users = list(
                party.participants.values_list("username", flat=True),
            )
        except WatchParty.DoesNotExist:
            return []

        online = _online_set(self.party_id)
        return [{"username": u, "online": u in online} for u in db_users]

    @database_sync_to_async
    def get_last_messages(self, limit=50):
        from rooms.models import ChatMessage

        messages = ChatMessage.objects.filter(room_id=self.party_id).order_by(
            "-created_at",
        )[:limit]
        return [
            {
                "username": m.user.username if m.user else "Система",
                "message": m.content,
                "system": m.is_system,
                "timestamp": m.created_at.isoformat(),
            }
            for m in reversed(messages)
        ]

    @database_sync_to_async
    def save_message(self, content, username=None, is_system=False):
        from rooms.models import ChatMessage, WatchParty

        user = None
        if username and not is_system and self.user.is_authenticated:
            user = self.user

        room = WatchParty.objects.get(id=self.party_id)
        ChatMessage.objects.create(
            room=room,
            user=user,
            content=content,
            is_system=is_system,
        )

    @database_sync_to_async
    def save_watchparty_video(self, video_id):
        from rooms.models import WatchParty
        from upload.models import Video

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
        from rooms.models import WatchParty

        try:
            return WatchParty.objects.select_related("video").get(
                id=self.party_id,
            )
        except WatchParty.DoesNotExist:
            return None

    @database_sync_to_async
    def set_watchparty_state(
        self,
        time,
        ts,
        is_playing,
        video_id=None,
        hls_url=None,
    ):
        key = _state_key(self.party_id)
        state = {
            "time": float(time or 0.0),
            "ts": int(ts) if ts is not None else int(_time.time() * 1000),
            "is_playing": bool(is_playing),
            "video_id": int(video_id) if video_id is not None else None,
            "hls_url": str(hls_url) if hls_url else None,
        }
        cache.set(key, state, None)  # persist until invalidated
        return True

    @database_sync_to_async
    def get_watchparty_state(self):
        from rooms.models import WatchParty

        key = _state_key(self.party_id)
        st = cache.get(key)
        if st:
            return st
        # Fallback: build from DB room.video
        try:
            room = WatchParty.objects.select_related("video").get(
                id=self.party_id,
            )
            if room.video and getattr(room.video, "hls_manifest", None):
                return {
                    "time": 0.0,
                    "ts": int(_time.time() * 1000),
                    "is_playing": False,
                    "video_id": room.video.id,
                    "hls_url": room.video.hls_manifest.url,
                }
        except WatchParty.DoesNotExist:
            return None

        return None

    async def sync_broadcast(self, text_data):
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "broadcast", "text": text_data},
        )
