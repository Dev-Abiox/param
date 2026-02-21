"""
ASGI config for Clinomic project.

Routes HTTP through Django and WebSocket through Channels.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinomic.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing consumers.
django_asgi_app = get_asgi_application()

from apps.screening.middleware import JWTWebSocketMiddleware  # noqa: E402
from apps.screening.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        JWTWebSocketMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
