"""
Integration API views — inbound endpoint for external LIS systems.

POST /api/integration/inbound/<api_key>
    Receives CBC data from an external LIS, processes it, returns the
    B12 screening result in the endpoint's configured outbound format.

GET /api/integration/endpoints
    Lists configured endpoints for the current tenant (admin only).

POST /api/integration/endpoints
    Creates a new endpoint (admin only).

GET /api/integration/logs
    Recent integration logs for the current tenant (admin only).
"""

import secrets

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth_classes import IsMFAVerified, HasRole
from apps.core.models import Role

from .models import IntegrationEndpoint, IntegrationLog, IntegrationFormat
from .engine import process_inbound, IntegrationError


class InboundView(APIView):
    """
    POST /api/integration/inbound/<api_key>

    The LIS authenticates via the API key in the URL path (not JWT).
    This allows machine-to-machine communication without user tokens.

    Accepts the payload in the endpoint's configured inbound format.
    Returns the screening result in the configured outbound format.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'integration'

    def post(self, request, api_key):
        try:
            endpoint = IntegrationEndpoint.objects.get(api_key=api_key, is_active=True)
        except IntegrationEndpoint.DoesNotExist:
            return Response(
                {'error': 'Invalid or inactive integration key'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            screening_data, outbound_body, content_type = process_inbound(
                endpoint, request.body, request=request,
            )
        except IntegrationError as e:
            status_map = {
                'parse': status.HTTP_400_BAD_REQUEST,
                'predict': status.HTTP_503_SERVICE_UNAVAILABLE,
                'persist': status.HTTP_422_UNPROCESSABLE_ENTITY,
            }
            return Response(
                {'error': str(e), 'stage': e.stage},
                status=status_map.get(e.stage, status.HTTP_500_INTERNAL_SERVER_ERROR),
            )

        # Return in the endpoint's outbound format
        if content_type == 'application/json':
            return Response(screening_data)

        return Response(
            outbound_body,
            content_type=content_type,
            status=status.HTTP_200_OK,
        )


class EndpointListView(APIView):
    """
    GET  — list integration endpoints for the current org.
    POST — create a new endpoint (auto-generates API key).
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB]

    def get(self, request):
        endpoints = IntegrationEndpoint.objects.all().order_by('-created_at')
        data = [{
            'id': str(ep.id),
            'name': ep.name,
            'is_active': ep.is_active,
            'inbound_format': ep.inbound_format,
            'outbound_format': ep.outbound_format,
            'api_key': ep.api_key,
            'callback_url': ep.callback_url,
            'field_mapping': ep.field_mapping,
            'default_lab_code': ep.default_lab_code,
            'default_doctor_code': ep.default_doctor_code,
            'auto_approve': ep.auto_approve,
            'created_at': ep.created_at.isoformat(),
        } for ep in endpoints]
        return Response(data)

    def post(self, request):
        d = request.data
        api_key = secrets.token_urlsafe(48)

        ep = IntegrationEndpoint.objects.create(
            name=d.get('name', 'Unnamed Endpoint'),
            inbound_format=d.get('inbound_format', IntegrationFormat.JSON),
            outbound_format=d.get('outbound_format', IntegrationFormat.JSON),
            api_key=api_key,
            callback_url=d.get('callback_url', ''),
            callback_headers=d.get('callback_headers', {}),
            field_mapping=d.get('field_mapping', {}),
            default_lab_code=d.get('default_lab_code', ''),
            default_doctor_code=d.get('default_doctor_code', ''),
            auto_approve=d.get('auto_approve', False),
        )

        return Response({
            'id': str(ep.id),
            'name': ep.name,
            'api_key': api_key,
            'inbound_url': f'/api/integration/inbound/{api_key}',
            'message': 'Save this API key — it will not be shown again.',
        }, status=status.HTTP_201_CREATED)


class EndpointDetailView(APIView):
    """PATCH/DELETE a single endpoint."""
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB]

    def patch(self, request, endpoint_id):
        try:
            ep = IntegrationEndpoint.objects.get(id=endpoint_id)
        except IntegrationEndpoint.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        updatable = [
            'name', 'is_active', 'inbound_format', 'outbound_format',
            'callback_url', 'callback_headers', 'field_mapping',
            'default_lab_code', 'default_doctor_code', 'auto_approve',
        ]
        for field in updatable:
            if field in request.data:
                setattr(ep, field, request.data[field])
        ep.save()

        return Response({'id': str(ep.id), 'status': 'updated'})

    def delete(self, request, endpoint_id):
        try:
            ep = IntegrationEndpoint.objects.get(id=endpoint_id)
        except IntegrationEndpoint.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        ep.is_active = False
        ep.save(update_fields=['is_active'])
        return Response({'id': str(ep.id), 'status': 'deactivated'})


class IntegrationLogView(APIView):
    """GET recent integration logs for debugging."""
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB]

    def get(self, request):
        qs = IntegrationLog.objects.select_related('endpoint').order_by('-created_at')[:100]
        data = [{
            'id': str(log.id),
            'endpoint': log.endpoint.name,
            'direction': log.direction,
            'status': log.status,
            'error_detail': log.error_detail,
            'screening_id': str(log.screening_id) if log.screening_id else None,
            'duration_ms': log.duration_ms,
            'created_at': log.created_at.isoformat(),
        } for log in qs]
        return Response(data)
