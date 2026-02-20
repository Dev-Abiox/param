"""
WebSocket consumers for real-time notifications.

WorkQueueConsumer:   Broadcasts screening status changes to LAB users.
DoctorAlertConsumer: Pushes high-risk screening alerts to DOCTOR users.

Security:
- JWT authenticated via JWTWebSocketMiddleware
- Tenant-isolated channel groups (group name includes schema_name)
- No PHI transmitted: only screening IDs, status, and risk_class
"""

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class WorkQueueConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket for LAB work queue real-time updates.

    Group: wq_{schema_name}

    Receives messages when:
    - A new screening is created (status=pending)
    - A screening status changes

    Only LAB and ADMIN roles can connect.
    """

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        role = getattr(user, 'role', '')
        if role not in ('LAB', 'ADMIN'):
            await self.close(code=4003)
            return

        tenant = self.scope.get('tenant')
        schema = getattr(tenant, 'schema_name', 'public') if tenant else 'public'
        self.group_name = f'wq_{schema}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            "ws_queue_connect",
            extra={'user': user.username, 'group': self.group_name},
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Clients should not send data; ignore gracefully
        pass

    async def screening_status_change(self, event):
        """
        Handler for screening.status_change channel layer events.

        Event shape:
        {
            'type': 'screening.status_change',
            'screening_id': str,
            'old_status': str,
            'new_status': str,
            'risk_class': int,
            'timestamp': str (ISO 8601),
        }
        """
        await self.send_json({
            'type': 'status_change',
            'screeningId': event['screening_id'],
            'oldStatus': event['old_status'],
            'newStatus': event['new_status'],
            'riskClass': event['risk_class'],
            'timestamp': event['timestamp'],
        })

    async def screening_new(self, event):
        """
        Handler for new screening creation.

        Event shape:
        {
            'type': 'screening.new',
            'screening_id': str,
            'risk_class': int,
            'status': str,
            'timestamp': str,
        }
        """
        await self.send_json({
            'type': 'new_screening',
            'screeningId': event['screening_id'],
            'riskClass': event['risk_class'],
            'status': event['status'],
            'timestamp': event['timestamp'],
        })


class DoctorAlertConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket for DOCTOR high-risk alert notifications.

    Group: alerts_{schema_name}_{doctor_id}  (for DOCTORs)
           alerts_{schema_name}_all          (for ADMINs)

    Receives messages when:
    - A screening linked to this doctor is classified as DEFICIENT (risk_class=3)

    Only DOCTOR and ADMIN roles can connect.
    """

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        role = getattr(user, 'role', '')
        if role not in ('DOCTOR', 'ADMIN'):
            await self.close(code=4003)
            return

        tenant = self.scope.get('tenant')
        schema = getattr(tenant, 'schema_name', 'public') if tenant else 'public'

        # For DOCTOR role, subscribe to their specific doctor group
        # For ADMIN role, subscribe to the tenant-wide alert group
        if role == 'DOCTOR':
            doctor_id = await self._get_doctor_id(user.email)
            if not doctor_id:
                await self.close(code=4003)
                return
            self.group_name = f'alerts_{schema}_{doctor_id}'
        else:
            # ADMIN sees all high-risk alerts in the tenant
            self.group_name = f'alerts_{schema}_all'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        pass

    async def screening_high_risk(self, event):
        """
        Handler for high-risk screening alert.

        Event shape (NO PHI):
        {
            'type': 'screening.high_risk',
            'screening_id': str,
            'risk_class': int,
            'label_text': str,
            'timestamp': str,
        }
        """
        await self.send_json({
            'type': 'high_risk_alert',
            'screeningId': event['screening_id'],
            'riskClass': event['risk_class'],
            'labelText': event['label_text'],
            'timestamp': event['timestamp'],
        })

    @database_sync_to_async
    def _get_doctor_id(self, email):
        from apps.screening.models import Doctor
        doctor = Doctor.objects.filter(email=email, is_active=True).first()
        return str(doctor.id) if doctor else None
