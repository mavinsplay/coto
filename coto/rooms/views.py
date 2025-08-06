from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

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


class JoinRoomView(LoginRequiredMixin, View):
    def post(self, request, pk):
        room = get_object_or_404(WatchParty, pk=pk)
        if room.participants.count() >= room.limit_participants:
            messages.error(request, "Лимит участников достигнут.")
        else:
            room.participants.add(request.user)
            messages.success(
                request,
                f"Вы присоединились к комнате «{room.name}».",
            )

        return redirect(reverse("rooms:detail", kwargs={"pk": room.pk}))


class LeaveRoomView(LoginRequiredMixin, View):
    def post(self, request, pk):
        room = get_object_or_404(WatchParty, pk=pk)
        room.participants.remove(request.user)
        messages.success(request, f"Вы покинули комнату «{room.name}».")
        return redirect(reverse("rooms:list"))
