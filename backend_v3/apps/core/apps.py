from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        # Wire up post_schema_sync so new tenant schemas get CRUD grants
        # for the least-privilege app role automatically. No-op when
        # POSTGRES_APP_USER is unset (single-role legacy mode).
        from . import signals
        signals.connect_signals()
