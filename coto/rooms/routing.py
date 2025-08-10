from django.urls import re_path

from rooms import consumers

websocket_urlpatterns = [
    re_path(
        r"ws/room/(?P<room_id>\d+)/$",
        consumers.WatchPartySyncConsumer.as_asgi(),
    ),
]
