import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from rooms.models import ChatMessage, WatchParty


__all__ = ("WatchPartySyncConsumer",)


class WatchPartySyncConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.party_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.group_name = f"watchparty_{self.party_id}"
        self.user = self.scope["user"]

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Отправляем историю сообщений
        history = await self.get_last_messages(limit=50)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "history",
                    "messages": history,
                },
            ),
        )

        # Отправляем список участников
        participants = await self.get_participants()
        await self.send(
            text_data=json.dumps(
                {
                    "type": "participants",
                    "participants": participants,
                },
            ),
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name,
        )

    async def receive(self, text_data):
        """
        Обработка входящих данных:
        - Если JSON и type=chat → чат
        - Если строка или JSON без type → синхронизация видео
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            # Старый формат синхронизации (просто строка)
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

                # Сохраняем в БД
                await self.save_message(
                    message, username, data.get("system", False),
                )

                # Отправляем в группу
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "chat_message",
                        "message": message,
                        "username": username,
                        "system": data.get("system", False),
                    },
                )

        elif msg_type == "participants_update":
            # Отправка обновлённого списка участников
            participants = await self.get_participants()
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "participants_update", "participants": participants},
            )

        else:
            # Всё остальное → синхронизация видео
            await self.sync_broadcast(text_data)

    # ========== Чат ==========
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
                },
            ),
        )

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

    # ========== Синхронизация ==========
    async def sync_broadcast(self, text_data):
        """
        Передача данных синхронизации видео в группу.
        """
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast",
                "text": text_data,
            },
        )

    async def broadcast(self, event):
        await self.send(text_data=event["text"])
