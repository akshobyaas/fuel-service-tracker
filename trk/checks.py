"""
Deployment-time system checks.

These run automatically with `manage.py check`, `manage.py migrate`,
`manage.py runserver`, etc. They don't change app behaviour — they just
surface configuration footguns that are easy to miss until they cause data
loss in production.
"""
import os

from django.conf import settings
from django.core.checks import Warning, register


@register()
def storage_persistence_check(app_configs, **kwargs):
    """
    Warn when the app is running in production (DEBUG=False) without S3/B2
    storage enabled. Uploaded documents and avatars then live on local disk,
    which most PaaS free tiers (Render, Railway, Heroku, etc.) wipe on every
    redeploy or dyno/instance restart — silently deleting user files with no
    error at upload time.
    """
    warnings = []
    if not settings.DEBUG and os.environ.get('USE_S3') != 'True':
        warnings.append(
            Warning(
                'USE_S3 is not enabled while DEBUG=False. Uploaded documents '
                'and avatars are being written to local disk, which is not '
                'guaranteed to persist across deploys/restarts on most '
                'hosting platforms.',
                hint=(
                    'If your hosting platform does not give this app a '
                    'persistent disk, set USE_S3=True along with '
                    'AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / '
                    'AWS_STORAGE_BUCKET_NAME / AWS_S3_ENDPOINT_URL '
                    '(e.g. Backblaze B2) before accepting real uploads.'
                ),
                id='trk.W001',
            )
        )
    return warnings
