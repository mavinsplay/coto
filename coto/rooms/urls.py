from django.urls import path

from rooms.views import (
    JoinPrivateRoomView,
    JoinRoomView,
    LeaveRoomView,
    RoomCreateView,
    RoomDeleteView,
    RoomDetailView,
    RoomManageView,
    RoomsView,
    RoomUpdateView,
)


app_name = "rooms"

urlpatterns = [
    path("", RoomsView.as_view(), name="list"),
    path("create/", RoomCreateView.as_view(), name="create"),
    path("manage/", RoomManageView.as_view(), name="manage"),
    path("join-private/", JoinPrivateRoomView.as_view(), name="join_private"),
    path("<int:pk>/", RoomDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", RoomUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", RoomDeleteView.as_view(), name="delete"),
    path("<int:pk>/join/", JoinRoomView.as_view(), name="join"),
    path("<int:pk>/leave/", LeaveRoomView.as_view(), name="leave"),
]
