"""
WebSocket JWT authentication middleware — first-message auth pattern.

The client opens the connection without a token in the URL, then sends:

    {"type": "auth", "token": "<JWT access token>"}

The middleware validates the token, attaches user/tenant to scope, sends
back {"type": "auth_ok"}, then delegates to the inner consumer.

If no valid auth message arrives within AUTH_TIMEOUT_S (5 s) the
connection is closed with code 4001.

This avoids placing the JWT in the query string where it would appear in
server logs, browser history, and proxy logs (H9).
"""

import asyncio
import json
import logging

import jwt
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_S = 5


class _AuthError(Exception):
    """Raised when auth fails during the first-message handshake."""
    def __init__(self, code: int):
        self.code = code


class JWTWebSocketMiddleware(BaseMiddleware):
    """
    First-message JWT authentication for WebSocket connections.

    Protocol:
        1. Client opens ws://host/ws/queue/ (no token in URL)
        2. Client sends: {"type": "auth", "token": "<access_token>"}
        3. Server responds: {"type": "auth_ok"} or closes with 4001/4003

    Populates scope['user'], scope['tenant'], and scope['token_payload'].
    """

    async def __call__(self, scope, receive, send):
        # Accept the WebSocket connection first
        await send({'type': 'websocket.accept'})

        # Wait for the auth message within the timeout
        try:
            token = await asyncio.wait_for(
                self._wait_for_auth(receive, send),
                timeout=AUTH_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            await self._send_auth_error(send, 'Auth timeout')
            await send({'type': 'websocket.close', 'code': 4001})
            return
        except _AuthError as exc:
            await send({'type': 'websocket.close', 'code': exc.code})
            return

        if token is None:
            # Client disconnected before sending auth
            return

        # Validate the JWT
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                audience='clinomic',
                issuer='clinomic',
            )
        except jwt.ExpiredSignatureError:
            await self._send_auth_error(send, 'Token expired')
            await send({'type': 'websocket.close', 'code': 4001})
            return
        except jwt.InvalidTokenError:
            await self._send_auth_error(send, 'Invalid token')
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

        # Set tenant from org_id — reject if missing or invalid
        org_id = payload.get('org_id')
        if not org_id:
            await send({'type': 'websocket.close', 'code': 4003})
            return

        tenant = await self._get_tenant(org_id)
        if not tenant:
            await send({'type': 'websocket.close', 'code': 4003})
            return

        scope['tenant'] = tenant
        await self._set_tenant_schema(tenant)

        # Confirm auth success
        await send({
            'type': 'websocket.send',
            'text': json.dumps({'type': 'auth_ok'}),
        })

        # Delegate to the inner application (consumer).
        # Wrap send so the consumer's accept() is a no-op (already accepted).
        async def wrapped_send(message):
            if message['type'] == 'websocket.accept':
                return  # swallow — already accepted by middleware
            await send(message)

        return await self.inner(scope, receive, wrapped_send)

    async def _wait_for_auth(self, receive, send):
        """Wait for the first websocket.receive with type=auth."""
        while True:
            message = await receive()

            if message['type'] == 'websocket.disconnect':
                return None

            if message['type'] == 'websocket.receive':
                text = message.get('text', '')
                try:
                    data = json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    await self._send_auth_error(send, 'Expected JSON auth message')
                    raise _AuthError(4001)

                if data.get('type') == 'auth' and data.get('token'):
                    return data['token']

                await self._send_auth_error(send, 'Send {"type":"auth","token":"..."} first')
                raise _AuthError(4001)

    @staticmethod
    async def _send_auth_error(send, detail):
        await send({
            'type': 'websocket.send',
            'text': json.dumps({'type': 'auth_error', 'detail': detail}),
        })

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
