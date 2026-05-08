from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root if present
_env_file = BASE_DIR / '.env'
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-smartolt-dev-key-change-in-production-xyz123')

DEBUG = os.environ.get('DEBUG', 'True').lower() not in ('false', '0', 'no')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_celery_beat',
    'django_celery_results',
    'accounts',
    'olts',
    'onts',
    'monitoring',
    'alerts',
    'reports',
    'core',
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

ROOT_URLCONF = 'smartolt.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.global_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'smartolt.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/olts/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

MESSAGE_STORAGE = 'django.contrib.messages.storage.cookie.CookieStorage'

from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}

# ── Cache (used by context processors; switch to Redis in production) ─────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# ── Celery ────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'default'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE
# Max 20 concurrent SSH connections per worker
CELERY_WORKER_CONCURRENCY = int(os.environ.get('CELERY_CONCURRENCY', 20))

# ── OLT connectivity ──────────────────────────────────────────────────────────
OLT_SSH_TIMEOUT = int(os.environ.get('OLT_SSH_TIMEOUT', 30))
OLT_SSH_MAX_CONCURRENT = int(os.environ.get('OLT_SSH_MAX_CONCURRENT', 50))

# ── Celery toggle ─────────────────────────────────────────────────────────────
# Set USE_CELERY=False in .env to run all tasks synchronously (no Redis needed)
USE_CELERY = os.environ.get('USE_CELERY', 'True').lower() not in ('false', '0', 'no')

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
            'datefmt': '%H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'olts': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

