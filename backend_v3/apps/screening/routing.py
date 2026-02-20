"""
WebSocket URL routing for the screening app.
"""

from django.urls import re_path

from .consumers import DoctorAlertConsumer, WorkQueueConsumer

websocket_urlpatterns = [
    re_path(r'ws/queue/$', WorkQueueConsumer.as_asgi()),
    re_path(r'ws/alerts/$', DoctorAlertConsumer.as_asgi()),
]
