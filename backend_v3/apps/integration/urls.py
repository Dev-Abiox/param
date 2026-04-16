from django.urls import path

from .views import InboundView, EndpointListView, EndpointDetailView, IntegrationLogView

urlpatterns = [
    # Machine-to-machine: LIS pushes CBC data here (auth via api_key in URL)
    path('inbound/<str:api_key>', InboundView.as_view(), name='integration-inbound'),

    # Admin: manage integration endpoints
    path('endpoints', EndpointListView.as_view(), name='integration-endpoints'),
    path('endpoints/<uuid:endpoint_id>', EndpointDetailView.as_view(), name='integration-endpoint-detail'),

    # Admin: view integration logs
    path('logs', IntegrationLogView.as_view(), name='integration-logs'),
]
