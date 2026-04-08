"""
Tests for WebSocket broadcast helpers and consumer role enforcement.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.screening.ws_broadcast import (
    broadcast_high_risk_alert,
    broadcast_new_screening,
    broadcast_status_change,
)


# ── Broadcast helper tests ───────────────────────────────────────────────────


class TestBroadcastStatusChange:

    @patch("apps.screening.ws_broadcast.get_channel_layer")
    @patch("apps.screening.ws_broadcast._get_schema_name", return_value="test_schema")
    def test_sends_to_correct_group(self, _mock_schema, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        broadcast_status_change("abc-123", "pending", "in_progress", 1)

        mock_layer.group_send.assert_called_once()
        call_args = mock_layer.group_send.call_args
        group = call_args[0][0]
        message = call_args[0][1]

        assert group == "wq_test_schema"
        assert message["type"] == "screening.status_change"
        assert message["screening_id"] == "abc-123"
        assert message["old_status"] == "pending"
        assert message["new_status"] == "in_progress"
        assert message["risk_class"] == 1
        assert "timestamp" in message

    @patch("apps.screening.ws_broadcast.get_channel_layer")
    def test_no_channel_layer_does_not_raise(self, mock_get_layer):
        mock_get_layer.return_value = None
        # Should not raise
        broadcast_status_change("abc", "pending", "in_progress", 1)

    @patch("apps.screening.ws_broadcast.get_channel_layer")
    def test_exception_is_caught(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = MagicMock(side_effect=RuntimeError("redis down"))
        mock_get_layer.return_value = mock_layer

        # Should not raise
        broadcast_status_change("abc", "pending", "in_progress", 1)


class TestBroadcastNewScreening:

    @patch("apps.screening.ws_broadcast.get_channel_layer")
    @patch("apps.screening.ws_broadcast._get_schema_name", return_value="clinic1")
    def test_sends_correct_message(self, _mock_schema, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        broadcast_new_screening("s-99", 2, "pending")

        call_args = mock_layer.group_send.call_args
        group = call_args[0][0]
        message = call_args[0][1]

        assert group == "wq_clinic1"
        assert message["type"] == "screening.new"
        assert message["screening_id"] == "s-99"
        assert message["risk_class"] == 2
        assert message["status"] == "pending"


class TestBroadcastHighRiskAlert:

    @patch("apps.screening.ws_broadcast.get_channel_layer")
    @patch("apps.screening.ws_broadcast._get_schema_name", return_value="tenant_a")
    def test_sends_to_doctor_and_admin_groups(self, _mock_schema, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        doctor_id = str(uuid.uuid4())
        broadcast_high_risk_alert("s-1", 3, "DEFICIENT", doctor_id)

        assert mock_layer.group_send.call_count == 2

        calls = mock_layer.group_send.call_args_list
        groups = {c[0][0] for c in calls}
        assert f"alerts_tenant_a_{doctor_id}" in groups
        assert "alerts_tenant_a_all" in groups

        # All messages should have the right type
        for c in calls:
            msg = c[0][1]
            assert msg["type"] == "screening.high_risk"
            assert msg["screening_id"] == "s-1"
            assert msg["label_text"] == "DEFICIENT"

    @patch("apps.screening.ws_broadcast.get_channel_layer")
    def test_non_deficient_does_not_broadcast(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        # risk_class=2 should not fire
        broadcast_high_risk_alert("s-2", 2, "BORDERLINE")
        mock_layer.group_send.assert_not_called()

        # risk_class=1 should not fire either
        broadcast_high_risk_alert("s-3", 1, "NORMAL")
        mock_layer.group_send.assert_not_called()

    @patch("apps.screening.ws_broadcast.get_channel_layer")
    @patch("apps.screening.ws_broadcast._get_schema_name", return_value="pub")
    def test_no_doctor_sends_only_admin_group(self, _mock_schema, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        broadcast_high_risk_alert("s-5", 3, "DEFICIENT", doctor_id=None)

        assert mock_layer.group_send.call_count == 1
        group = mock_layer.group_send.call_args[0][0]
        assert group == "alerts_pub_all"


# ── Consumer role enforcement tests ──────────────────────────────────────────


class TestWorkQueueConsumerRoles:

    @pytest.mark.asyncio
    async def test_rejects_unauthenticated(self):
        from apps.screening.consumers import WorkQueueConsumer

        consumer = WorkQueueConsumer()
        consumer.scope = {"user": None}
        consumer.channel_layer = AsyncMock()
        consumer.channel_name = "test-channel"
        consumer.close = AsyncMock()
        consumer.accept = AsyncMock()

        await consumer.connect()
        consumer.close.assert_called_with(code=4001)
        consumer.accept.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_doctor_role(self):
        from apps.screening.consumers import WorkQueueConsumer

        user = MagicMock()
        user.is_authenticated = True
        user.role = "DOCTOR"

        consumer = WorkQueueConsumer()
        consumer.scope = {"user": user}
        consumer.channel_layer = AsyncMock()
        consumer.channel_name = "test-channel"
        consumer.close = AsyncMock()
        consumer.accept = AsyncMock()
        # Mock _check_user_active so the role check is reached (not the DB lookup)
        consumer._check_user_active = AsyncMock(return_value=True)

        await consumer.connect()
        consumer.close.assert_called_with(code=4003)
        consumer.accept.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_lab_role(self):
        from apps.screening.consumers import WorkQueueConsumer

        user = MagicMock()
        user.is_authenticated = True
        user.role = "LAB"
        user.username = "lab_user"

        tenant = MagicMock()
        tenant.schema_name = "clinic_x"

        consumer = WorkQueueConsumer()
        consumer.scope = {"user": user, "tenant": tenant}
        consumer.channel_layer = AsyncMock()
        consumer.channel_name = "test-channel"
        consumer.close = AsyncMock()
        consumer.accept = AsyncMock()
        consumer._check_user_active = AsyncMock(return_value=True)

        await consumer.connect()
        consumer.accept.assert_called_once()
        consumer.close.assert_not_called()

class TestDoctorAlertConsumerRoles:

    @pytest.mark.asyncio
    async def test_rejects_superadmin_role(self):
        from apps.screening.consumers import DoctorAlertConsumer

        user = MagicMock()
        user.is_authenticated = True
        user.role = "SUPER_ADMIN"

        consumer = DoctorAlertConsumer()
        consumer.scope = {"user": user}
        consumer.channel_layer = AsyncMock()
        consumer.channel_name = "test-channel"
        consumer.close = AsyncMock()
        consumer.accept = AsyncMock()
        consumer._check_user_active = AsyncMock(return_value=True)

        await consumer.connect()
        consumer.close.assert_called_with(code=4003)
        consumer.accept.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_lab_role(self):
        from apps.screening.consumers import DoctorAlertConsumer

        user = MagicMock()
        user.is_authenticated = True
        user.role = "LAB"

        tenant = MagicMock()
        tenant.schema_name = "t1"

        consumer = DoctorAlertConsumer()
        consumer.scope = {"user": user, "tenant": tenant}
        consumer.channel_layer = AsyncMock()
        consumer.channel_name = "test-channel"
        consumer.close = AsyncMock()
        consumer.accept = AsyncMock()
        consumer._check_user_active = AsyncMock(return_value=True)

        await consumer.connect()
        consumer.accept.assert_called_once()
        assert consumer.group_name == "alerts_t1_all"

    @pytest.mark.asyncio
    async def test_rejects_doctor_without_doctor_record(self):
        from apps.screening.consumers import DoctorAlertConsumer

        user = MagicMock()
        user.is_authenticated = True
        user.role = "DOCTOR"
        user.email = "doc@test.com"

        consumer = DoctorAlertConsumer()
        consumer.scope = {"user": user, "tenant": None}
        consumer.channel_layer = AsyncMock()
        consumer.channel_name = "test-channel"
        consumer.close = AsyncMock()
        consumer.accept = AsyncMock()
        consumer._check_user_active = AsyncMock(return_value=True)
        consumer._get_doctor_id = AsyncMock(return_value=None)

        await consumer.connect()
        consumer.close.assert_called_with(code=4003)
        consumer.accept.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_doctor_with_doctor_record(self):
        from apps.screening.consumers import DoctorAlertConsumer

        user = MagicMock()
        user.is_authenticated = True
        user.role = "DOCTOR"
        user.email = "doc@test.com"

        tenant = MagicMock()
        tenant.schema_name = "t2"

        doctor_id = str(uuid.uuid4())

        consumer = DoctorAlertConsumer()
        consumer.scope = {"user": user, "tenant": tenant}
        consumer.channel_layer = AsyncMock()
        consumer.channel_name = "test-channel"
        consumer.close = AsyncMock()
        consumer.accept = AsyncMock()
        consumer._get_doctor_id = AsyncMock(return_value=doctor_id)

        await consumer.connect()
        consumer.accept.assert_called_once()
        assert consumer.group_name == f"alerts_t2_{doctor_id}"
