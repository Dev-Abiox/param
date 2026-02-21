"""
Tests for JWTWebSocketMiddleware (first-message auth pattern).

The middleware:
1. Accepts the connection
2. Waits for {"type":"auth","token":"..."} within AUTH_TIMEOUT_S
3. Validates the JWT
4. Sends {"type":"auth_ok"} on success
5. Delegates to the inner consumer
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from django.conf import settings

from apps.screening.middleware import AUTH_TIMEOUT_S, JWTWebSocketMiddleware


def _make_token(payload_overrides=None, secret=None):
    """Create a JWT with sensible defaults."""
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(uuid.uuid4()),
        'org_id': str(uuid.uuid4()),
        'token_type': 'access',
        'mfa_verified': True,
        'exp': now + timedelta(minutes=30),
        'iat': now,
    }
    if payload_overrides:
        payload.update(payload_overrides)
    return jwt.encode(
        payload,
        secret or settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def _auth_receive(token):
    """Return a receive callable that delivers an auth message."""
    msg = {'type': 'websocket.receive', 'text': json.dumps({'type': 'auth', 'token': token})}
    return AsyncMock(return_value=msg)


def _collector():
    """Return (send, sent_list) where send appends to the list."""
    sent = []
    async def send(message):
        sent.append(message)
    return send, sent


class TestValidAuth:

    @pytest.mark.asyncio
    async def test_valid_token_sets_scope_and_delegates(self):
        """Full happy path: accept -> auth -> auth_ok -> inner called."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        user = MagicMock(is_active=True, is_authenticated=True)
        tenant = MagicMock()
        token = _make_token()

        scope = {'type': 'websocket'}
        receive = _auth_receive(token)
        send, sent = _collector()

        with patch.object(mw, '_get_user', new=AsyncMock(return_value=user)), \
             patch.object(mw, '_get_tenant', new=AsyncMock(return_value=tenant)), \
             patch.object(mw, '_set_tenant_schema', new=AsyncMock()):
            await mw(scope, receive, send)

        # First message: websocket.accept
        assert sent[0] == {'type': 'websocket.accept'}
        # Second message: auth_ok
        auth_ok = json.loads(sent[1]['text'])
        assert auth_ok['type'] == 'auth_ok'

        # Scope populated
        assert scope['user'] is user
        assert scope['tenant'] is tenant
        assert 'token_payload' in scope

        # Inner app called
        inner.assert_called_once()


class TestExpiredToken:

    @pytest.mark.asyncio
    async def test_expired_token_closes_4001(self):
        """An expired JWT should close with code 4001."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        token = _make_token({'exp': datetime.now(timezone.utc) - timedelta(hours=1)})

        scope = {'type': 'websocket'}
        receive = _auth_receive(token)
        send, sent = _collector()

        await mw(scope, receive, send)

        codes = [m.get('code') for m in sent if m.get('type') == 'websocket.close']
        assert 4001 in codes
        inner.assert_not_called()


class TestInvalidToken:

    @pytest.mark.asyncio
    async def test_garbage_token_closes_4001(self):
        """A malformed JWT should close with code 4001."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        scope = {'type': 'websocket'}
        receive = _auth_receive('not.a.jwt')
        send, sent = _collector()

        await mw(scope, receive, send)

        codes = [m.get('code') for m in sent if m.get('type') == 'websocket.close']
        assert 4001 in codes


class TestNonAccessToken:

    @pytest.mark.asyncio
    async def test_refresh_token_closes_4001(self):
        """A refresh token should be rejected with 4001."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        token = _make_token({'token_type': 'refresh'})
        scope = {'type': 'websocket'}
        receive = _auth_receive(token)
        send, sent = _collector()

        await mw(scope, receive, send)

        codes = [m.get('code') for m in sent if m.get('type') == 'websocket.close']
        assert 4001 in codes


class TestMFANotVerified:

    @pytest.mark.asyncio
    async def test_mfa_false_closes_4003(self):
        """Token with mfa_verified=False should close with 4003."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        token = _make_token({'mfa_verified': False})
        scope = {'type': 'websocket'}
        receive = _auth_receive(token)
        send, sent = _collector()

        await mw(scope, receive, send)

        codes = [m.get('code') for m in sent if m.get('type') == 'websocket.close']
        assert 4003 in codes


class TestInactiveUser:

    @pytest.mark.asyncio
    async def test_inactive_user_closes_4001(self):
        """An inactive user should be rejected."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        user = MagicMock(is_active=False)
        token = _make_token()

        scope = {'type': 'websocket'}
        receive = _auth_receive(token)
        send, sent = _collector()

        with patch.object(mw, '_get_user', new=AsyncMock(return_value=user)):
            await mw(scope, receive, send)

        codes = [m.get('code') for m in sent if m.get('type') == 'websocket.close']
        assert 4001 in codes


class TestBadFirstMessage:

    @pytest.mark.asyncio
    async def test_non_json_closes_4001(self):
        """Non-JSON first message should close with 4001."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        receive = AsyncMock(return_value={
            'type': 'websocket.receive',
            'text': 'this is not json {{{',
        })
        scope = {'type': 'websocket'}
        send, sent = _collector()

        await mw(scope, receive, send)

        codes = [m.get('code') for m in sent if m.get('type') == 'websocket.close']
        assert 4001 in codes

    @pytest.mark.asyncio
    async def test_wrong_type_field_closes_4001(self):
        """First message with wrong type field should close with 4001."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        receive = AsyncMock(return_value={
            'type': 'websocket.receive',
            'text': json.dumps({'type': 'subscribe', 'channel': 'foo'}),
        })
        scope = {'type': 'websocket'}
        send, sent = _collector()

        await mw(scope, receive, send)

        codes = [m.get('code') for m in sent if m.get('type') == 'websocket.close']
        assert 4001 in codes


class TestClientDisconnect:

    @pytest.mark.asyncio
    async def test_disconnect_before_auth_exits_cleanly(self):
        """Client disconnecting before sending auth should exit without error."""
        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        receive = AsyncMock(return_value={'type': 'websocket.disconnect'})
        scope = {'type': 'websocket'}
        send, sent = _collector()

        await mw(scope, receive, send)

        assert sent[0] == {'type': 'websocket.accept'}
        inner.assert_not_called()


class TestAuthTimeout:

    @pytest.mark.asyncio
    async def test_timeout_closes_4001(self):
        """If no auth message arrives within the timeout, close with 4001."""
        import apps.screening.middleware as mw_mod

        inner = AsyncMock()
        mw = JWTWebSocketMiddleware(inner)

        async def hang():
            await asyncio.sleep(60)

        receive = AsyncMock(side_effect=hang)
        scope = {'type': 'websocket'}
        send, sent = _collector()

        original = mw_mod.AUTH_TIMEOUT_S
        mw_mod.AUTH_TIMEOUT_S = 0.1
        try:
            await mw(scope, receive, send)
        finally:
            mw_mod.AUTH_TIMEOUT_S = original

        codes = [m.get('code') for m in sent if m.get('type') == 'websocket.close']
        assert 4001 in codes
