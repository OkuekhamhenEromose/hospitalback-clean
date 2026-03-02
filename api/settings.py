import os
import logging
from pathlib import Path
from decouple import config, Csv
from datetime import timedelta
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)

# ========== SECURITY ==========
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,.onrender.com', cast=Csv())

ROOT_URLCONF = 'api.urls'
WSGI_APPLICATION = 'api.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 3rd party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'storages',
    'django_filters',
    'django_redis',

    # local apps
    'users.apps.UsersConfig',
    'hospital.apps.HospitalConfig',
    'social_django',
]

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ========== DATABASE ==========
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default='sqlite:///db.sqlite3'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ========== CACHE ==========
REDIS_URL = config('REDIS_URL', default='')

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_CLASS': 'redis.BlockingConnectionPool',
                'CONNECTION_POOL_CLASS_KWARGS': {
                    'max_connections': 50,
                    'timeout': 20,
                },
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
                'COMPRESS_MIN_LEN': 1024,
                'SERIALIZER': 'django_redis.serializers.json.JSONSerializer',
            },
            'KEY_PREFIX': 'hospital',
            'TIMEOUT': 300,
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'


# ========== CACHE UTILITY ==========
# FIX: cache.delete_pattern() only exists on django-redis. Calling it on
# LocMemCache (used in local dev or when Redis is down) raises AttributeError
# and crashes the request. Import and use this helper everywhere instead of
# calling cache.delete_pattern() directly in views.py and tasks.py.
def safe_cache_delete_pattern(pattern: str) -> None:
    """Delete cache keys matching pattern. Silent no-op on LocMemCache."""
    from django.core.cache import cache
    try:
        cache.delete_pattern(pattern)
    except AttributeError:
        # LocMemCache has no delete_pattern — safe to ignore in local dev
        pass


# ========== CELERY ==========
CELERY_BROKER_URL = REDIS_URL if REDIS_URL else 'memory://'
CELERY_RESULT_BACKEND = REDIS_URL if REDIS_URL else 'cache+memory://'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
# When Redis is unavailable (local dev), tasks run synchronously inline
CELERY_TASK_ALWAYS_EAGER = not bool(REDIS_URL)
CELERY_TASK_EAGER_PROPAGATES = True


# ========== STATIC FILES ==========
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_USE_FINDERS = True
WHITENOISE_MANIFEST_STRICT = False
WHITENOISE_ALLOW_ALL_ORIGINS = True


# ========== MEDIA FILES ==========
AWS_ACCESS_KEY_ID     = config('AWS_ACCESS_KEY_ID',     default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME    = config('AWS_S3_REGION_NAME',    default='eu-north-1')

AWS_CREDENTIALS_PROVIDED = all([
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_STORAGE_BUCKET_NAME,
])

if AWS_CREDENTIALS_PROVIDED:
    # FIX: replaced print() with logger — print() is unstructured and ignored
    # by log aggregators on Render.com.
    logger.info('AWS S3 credentials found — using S3 storage')

    # ── DO NOT set AWS_S3_CUSTOM_DOMAIN ──────────────────────────────────────
    #
    # AWS_S3_CUSTOM_DOMAIN is the single root cause of broken image URLs.
    # S3Boto3Storage.url() short-circuits to an UNSIGNED URL when custom_domain
    # is truthy — AWS_QUERYSTRING_AUTH is never reached. Unsigned URLs return
    # 403 on any private bucket (the AWS default since April 2023).
    #
    # Without this setting, self.custom_domain = None, so url() falls through
    # to generate_presigned_url() and returns a signed URL that works on
    # private buckets with no AWS console changes needed.

    AWS_S3_USE_SSL        = True
    AWS_S3_SECURE_URLS    = True
    AWS_S3_FILE_OVERWRITE = False

    # eu-north-1 only accepts Signature Version 4.
    AWS_S3_SIGNATURE_VERSION = 's3v4'

    # Presigned URLs — only reached because custom_domain is unset (None).
    AWS_QUERYSTRING_AUTH   = True
    AWS_QUERYSTRING_EXPIRE = 86400

    AWS_DEFAULT_ACL = None
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

    DEFAULT_FILE_STORAGE = 'hospital.storage_backends.MediaStorage'
    MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/media/'
else:
    logger.warning('AWS S3 credentials missing — using local filesystem storage')
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    MEDIA_URL  = '/media/'  # This already has trailing slash
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Used by serializers when constructing absolute local media URLs
BASE_URL = config('BASE_URL', default='http://localhost:8000')


# ========== JWT ==========
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}


# ========== DRF ==========
# ⚠️  PAGINATION NOTE
# LimitOffsetPagination wraps every list response as:
#   { "count": N, "next": "...", "previous": "...", "results": [...] }
# The frontend api.ts handles this via the unwrapList() helper.
# To disable pagination for a specific ViewSet, set:
#   pagination_class = None
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),
    # ── Pagination ────────────────────────────────────────────────────────
    # Responses are wrapped: {count, next, previous, results:[...]}
    # Frontend unwraps via unwrapList() in api.ts — do NOT remove that helper.
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20,
    # ─────────────────────────────────────────────────────────────────────
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
}

# FIX: Disable BrowsableAPIRenderer in production.
# The browsable API adds HTML rendering overhead on every response and
# exposes internal API structure to anyone who opens an endpoint in a browser.
# Only JSONRenderer is needed in production.
if not DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
        'rest_framework.renderers.JSONRenderer',
    ]


# ========== CORS ==========
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    cast=Csv(),
    default='http://localhost:3000,https://*.vercel.app',
)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    cast=Csv(),
    default='http://localhost:3000,https://*.vercel.app,https://*.onrender.com',
)


# ========== SESSION SECURITY ==========
if not DEBUG:
    SESSION_COOKIE_SECURE          = True
    SESSION_COOKIE_HTTPONLY        = True
    SESSION_COOKIE_SAMESITE        = 'Lax'
    CSRF_COOKIE_SECURE             = True
    CSRF_COOKIE_SAMESITE           = 'Lax'
    SECURE_SSL_REDIRECT            = True
    SECURE_HSTS_SECONDS            = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True


# ========== SOCIAL AUTH ==========
AUTHENTICATION_BACKENDS = (
    'social_core.backends.google.GoogleOAuth2',
    'django.contrib.auth.backends.ModelBackend',
)

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY    = config('SOCIAL_AUTH_GOOGLE_OAUTH2_KEY',    default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = config('SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET', default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE  = ['email', 'profile']


# ========== LOGGING ==========
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'level': 'WARNING',
        },
        # App-level loggers so hospital/ and users/ log at DEBUG in dev,
        # INFO in production — structured output visible in Render log stream.
        'hospital': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'users': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}


# ========== UPLOAD LIMITS ==========
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'