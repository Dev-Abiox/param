"""
WebSocket JWT authentication middleware.

Extracts the JWT from the query string (?token=xxx), validates it,
attaches the user and tenant to the scope. Rejects unauthenticated
connections with a close code.
"""

import logging
from urllib.parse import parse_qs

import jwt
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)


class JWTWebSocketMiddleware(BaseMiddleware):
    """
    Authenticate WebSocket connections via JWT query parameter.

    Usage: ws://host/ws/queue/?token=<access_token>

    Populates scope['user'], scope['tenant'], and scope['token_payload'].
    Closes connection if token is invalid or missing.
    """

    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode('utf-8')
        params = parse_qs(query_string)
        token = params.get('token', [None])[0]

        if not token:
            await send({'type': 'websocket.close', 'code': 4001})
            return

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            await send({'type': 'websocket.close', 'code': 4001})
            return
        except jwt.InvalidTokenError:
            await send({'type': 'websocket.close', 'code': 4001})
            return

        if payload.get('token_type') != 'access':
            await send({'type': 'websocket.close', 'code': 4001})
            return

        if not payload.get('mfa_verified', False):
            await send({'type': 'websocket.close', 'code': 4003})
            return

        # Resolve user
        user = await self._get_user(payload.get('sub'))
        if not user or not user.is_active:
            await send({'type': 'websocket.close', 'code': 4001})
            return

        scope['user'] = user
        scope['token_payload'] = payload

        # Set tenant from org_id
        org_id = payload.get('org_id')
        if org_id:
            tenant = await self._get_tenant(org_id)
            if tenant:
                scope['tenant'] = tenant
                await self._set_tenant_schema(tenant)

        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def _get_user(self, user_id):
        from apps.core.models import User
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def _get_tenant(self, org_id):
        from apps.core.models import Organization
        try:
            return Organization.objects.get(id=org_id, is_active=True)
        except Organization.DoesNotExist:
            return None

    @database_sync_to_async
    def _set_tenant_schema(self, tenant):
        connection.set_tenant(tenant)
