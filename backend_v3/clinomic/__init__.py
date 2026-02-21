# Clinomic B12 Screening Platform - Django Backend v3

# Import the Celery app so that shared_task decorators and Django's
# app registry pick it up whenever Django starts.
from .celery import app as celery_app  # noqa: F401

__all__ = ['celery_app']
