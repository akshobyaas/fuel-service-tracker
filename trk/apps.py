from django.apps import AppConfig


class TrkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trk'

    def ready(self):
        import trk.signals  # noqa: F401 — registers post_save signal
        import trk.checks   # noqa: F401 — registers deployment system checks
