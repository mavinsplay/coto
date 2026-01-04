import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
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
