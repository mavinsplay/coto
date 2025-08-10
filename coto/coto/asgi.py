import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
import django
from django.core.asgi import get_asgi_application

from rooms.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "coto.settings")
django.setup()

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(
                websocket_urlpatterns,
            ),
        ),
    },
)
