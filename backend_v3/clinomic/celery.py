"""
Celery application for Clinomic B12 Screening Platform.

Workers handle:
  - Data retention (purge expired tokens, old screenings)
  - Any future async tasks (email, reports, etc.)

Beat schedule is defined in settings.CELERY_BEAT_SCHEDULE.
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinomic.settings')

app = Celery('clinomic')

# Read configuration from Django settings, namespace CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Discover tasks in all installed INSTALLED_APPS
app.autodiscover_tasks()
