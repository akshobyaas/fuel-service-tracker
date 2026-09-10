from pathlib import Path
import os
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        # Fine for a throwaway local server; never used when DEBUG=False.
        SECRET_KEY = 'django-insecure-dev-only-do-not-use-in-production'
    else:
        # Refuse to boot with a guessable, hard-coded key. A fixed SECRET_KEY
        # lets anyone forge session cookies and CSRF tokens.
        raise ImproperlyConfigured(
            'SECRET_KEY environment variable must be set when DEBUG=False.'
        )

# -- Hosts & CSRF --
# Set these via env vars in production (e.g. on Render: "<app>.onrender.com"
# plus any custom domain). Do NOT add a wildcard here — it disables Django's
# Host-header validation entirely.
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()
]

DEFAULT_CSRF_ORIGINS = 'http://localhost:8000,http://127.0.0.1:8000'
CSRF_TRUSTED_ORIGINS = [
    h.strip() for h in os.environ.get('CSRF_TRUSTED_ORIGINS', DEFAULT_CSRF_ORIGINS).split(',') if h.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storages',
    'trk.apps.TrkConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'fstp.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

WSGI_APPLICATION = 'fstp.wsgi.application'

# -- Database --
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Asia/Kolkata'
USE_I18N      = True
USE_TZ        = True

# -- Email (used to deliver OTP codes) --
# Set EMAIL_HOST_USER / EMAIL_HOST_PASSWORD to send real emails (e.g. a Gmail
# address with an App Password: https://myaccount.google.com/apppasswords).
# Without those set, OTP emails are printed to the console instead of sent —
# fine for local development, not for anything real users will use.
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST    = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT    = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'PitLog <noreply@pitlog.local>')

# -- OTP tuning --
OTP_EXPIRY_MINUTES          = int(os.environ.get('OTP_EXPIRY_MINUTES', 10))
OTP_MAX_ATTEMPTS            = int(os.environ.get('OTP_MAX_ATTEMPTS', 5))
OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get('OTP_RESEND_COOLDOWN_SECONDS', 60))

# -- Static files --
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

_static_dir = BASE_DIR / 'static'
if _static_dir.is_dir():
    STATICFILES_DIRS = [_static_dir]

# -- Auth --
LOGIN_URL           = '/login/'
LOGIN_REDIRECT_URL  = '/'
LOGOUT_REDIRECT_URL = '/login/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
MESSAGE_STORAGE    = 'django.contrib.messages.storage.session.SessionStorage'

# -- Security --
if not DEBUG:
    # Needed whenever the app sits behind a TLS-terminating proxy (Render,
    # Railway, etc.) so Django knows the original request was HTTPS.
    SECURE_PROXY_SSL_HEADER     = ('HTTP_X_FORWARDED_PROTO', 'https')

    # Left off by default: only enable this once you've confirmed your host
    # reliably forwards X-Forwarded-Proto, otherwise it can cause redirect
    # loops behind certain proxies.
    SECURE_SSL_REDIRECT         = False

    SESSION_COOKIE_SECURE       = True
    CSRF_COOKIE_SECURE          = True
    SECURE_BROWSER_XSS_FILTER   = True
    SECURE_CONTENT_TYPE_NOSNIFF  = True

# -- Storage (Backblaze B2 / FileSystem + WhiteNoise for static files) --
if os.environ.get('USE_S3') == 'True':
    AWS_ACCESS_KEY_ID        = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY    = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME  = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_ENDPOINT_URL      = os.environ.get('AWS_S3_ENDPOINT_URL')
    AWS_S3_FILE_OVERWRITE    = False
    AWS_DEFAULT_ACL          = 'private'
    AWS_QUERYSTRING_AUTH     = True
    AWS_S3_SIGNATURE_VERSION = 's3v4'

    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }
    MEDIA_URL = f"{os.environ.get('AWS_S3_ENDPOINT_URL')}/{os.environ.get('AWS_STORAGE_BUCKET_NAME')}/"

else:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }
    MEDIA_URL  = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
