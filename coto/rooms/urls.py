from django.urls import path

from rooms.views import JoinRoomView, LeaveRoomView, RoomDetailView, RoomsView


app_name = "rooms"

urlpatterns = [
    path("", RoomsView.as_view(), name="list"),
    path("<int:pk>/", RoomDetailView.as_view(), name="detail"),
    path("<int:pk>/join/", JoinRoomView.as_view(), name="join"),
    path("<int:pk>/leave/", LeaveRoomView.as_view(), name="leave"),
]
