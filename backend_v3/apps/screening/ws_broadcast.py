"""
Channel layer broadcast helpers.

Sends messages to WebSocket consumers without any PHI.
All functions are synchronous (use async_to_sync internally).
"""

import logging
from datetime import datetime, timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connection

logger = logging.getLogger(__name__)


def _get_schema_name() -> str:
    return getattr(connection, 'schema_name', 'public')


def broadcast_status_change(
    screening_id: str,
    old_status: str,
    new_status: str,
    risk_class: int,
):
    """Broadcast a screening status change to the work queue group."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        schema = _get_schema_name()
        group = f'wq_{schema}'

        async_to_sync(channel_layer.group_send)(
            group,
            {
                'type': 'screening.status_change',
                'screening_id': str(screening_id),
                'old_status': old_status,
                'new_status': new_status,
                'risk_class': risk_class,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logger.warning("WebSocket broadcast failed: %s", e)


def broadcast_new_screening(screening_id: str, risk_class: int, status: str):
    """Broadcast a new screening creation to the work queue group."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        schema = _get_schema_name()
        group = f'wq_{schema}'

        async_to_sync(channel_layer.group_send)(
            group,
            {
                'type': 'screening.new',
                'screening_id': str(screening_id),
                'risk_class': risk_class,
                'status': status,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logger.warning("WebSocket broadcast failed: %s", e)


def broadcast_high_risk_alert(
    screening_id: str,
    risk_class: int,
    label_text: str,
    doctor_id: str | None = None,
):
    """
    Send high-risk alert to the doctor's alert group and the tenant-wide admin group.
    Only fires when risk_class == 3 (DEFICIENT).
    """
    if risk_class != 3:
        return

    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        schema = _get_schema_name()
        timestamp = datetime.now(timezone.utc).isoformat()
        message = {
            'type': 'screening.high_risk',
            'screening_id': str(screening_id),
            'risk_class': risk_class,
            'label_text': label_text,
            'timestamp': timestamp,
        }

        # Send to doctor-specific group
        if doctor_id:
            async_to_sync(channel_layer.group_send)(
                f'alerts_{schema}_{doctor_id}',
                message,
            )

        # Also send to admin-wide group
        async_to_sync(channel_layer.group_send)(
            f'alerts_{schema}_all',
            message,
        )
    except Exception as e:
        logger.warning("WebSocket high-risk broadcast failed: %s", e)
