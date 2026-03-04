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
    # Add your custom middleware (optional)
    # 'hospital.middleware.QueryCountDebugMiddleware',
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
# Get DATABASE_URL from environment (Render sets this automatically)
# For local development, you can set it in .env file
DATABASE_URL = config('DATABASE_URL', default='sqlite:///db.sqlite3')

# Parse database URL with dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,  # Always require SSL for PostgreSQL
    )
}

# Log which database we're using (helpful for debugging)
db_engine = DATABASES['default']['ENGINE']
logger.info(f"📊 Using database engine: {db_engine}")
if 'sqlite' in db_engine:
    logger.info(f"   SQLite database path: {DATABASES['default']['NAME']}")
else:
    logger.info(f"   PostgreSQL database host: {DATABASES['default'].get('HOST', 'unknown')}")

# Add PostgreSQL optimizations for production
if not DEBUG and 'postgresql' in db_engine:
    DATABASES['default']['OPTIONS'] = {
        'connect_timeout': 10,
        'keepalives': 1,
        'keepalives_idle': 30,
        'keepalives_interval': 10,
        'keepalives_count': 5,
        'options': '-c statement_timeout=30s',  # Prevent long-running queries
    }

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

# ========== CACHE ==========
REDIS_URL = config('REDIS_URL', default='')

# Check if hiredis is available for better performance
try:
    import hiredis
    HAS_HIREDIS = True
    logger.info("✅ hiredis installed - using fast Redis parser")
except ImportError:
    HAS_HIREDIS = False
    logger.warning("⚠️ hiredis not installed - using pure Python parser (slower)")

if REDIS_URL:
    CACHE_OPTIONS = {
        'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        'CONNECTION_POOL_CLASS': 'redis.BlockingConnectionPool',
        'CONNECTION_POOL_CLASS_KWARGS': {
            'max_connections': 50,
            'timeout': 20,
        },
        'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
        'COMPRESS_MIN_LEN': 1024,
        'SERIALIZER': 'django_redis.serializers.json.JSONSerializer',
        'PICKLE_VERSION': -1,
    }
    
    # Only add hiredis parser if available
    if HAS_HIREDIS:
        CACHE_OPTIONS['PARSER_CLASS'] = 'redis.connection.HiredisParser'
    
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': CACHE_OPTIONS,
            'KEY_PREFIX': 'hospital',
            'TIMEOUT': 300,
            'VERSION': 1,
        }
    }
    
    # Use Redis for session storage
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
    logger.info("✅ Redis cache configured successfully")
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'
    logger.info("⚠️ No Redis URL found - using local memory cache")


def safe_cache_delete_pattern(pattern: str) -> None:
    """Delete cache keys matching pattern. Silent no-op on LocMemCache."""
    from django.core.cache import cache
    try:
        cache.delete_pattern(pattern)
        logger.debug(f"Deleted cache pattern: {pattern}")
    except AttributeError:
        # LocMemCache has no delete_pattern — safe to ignore in local dev
        pass
    except Exception as e:
        logger.error(f"Error deleting cache pattern {pattern}: {e}")


# ========== CELERY ==========
CELERY_BROKER_URL = REDIS_URL if REDIS_URL else 'memory://'
CELERY_RESULT_BACKEND = REDIS_URL if REDIS_URL else 'cache+memory://'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = not bool(REDIS_URL)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000  # Prevent memory leaks
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fair task distribution

if REDIS_URL:
    logger.info("✅ Celery configured with Redis broker")
else:
    logger.warning("⚠️ No Redis URL found - Celery tasks will run synchronously")


# ========== STATIC FILES ==========
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_USE_FINDERS = True
WHITENOISE_MANIFEST_STRICT = False
WHITENOISE_ALLOW_ALL_ORIGINS = True


# ========== MEDIA FILES ==========
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='eu-north-1')

AWS_CREDENTIALS_PROVIDED = all([
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_STORAGE_BUCKET_NAME,
])

if AWS_CREDENTIALS_PROVIDED:
    logger.info('✅ AWS S3 credentials found — using S3 storage')

    AWS_S3_USE_SSL = True
    AWS_S3_SECURE_URLS = True
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_REGION_NAME = AWS_S3_REGION_NAME
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
        'ACL': 'public-read',
    }
    
    # Enable querystring auth for private buckets (required for eu-north-1)
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600  # URLs expire after 1 hour

    DEFAULT_FILE_STORAGE = 'hospital.storage_backends.MediaStorage'
    MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/media/'
else:
    logger.warning('⚠️ AWS S3 credentials missing — using local filesystem storage')
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    MEDIA_URL = '/media/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Used by serializers when constructing absolute local media URLs
BASE_URL = config('BASE_URL', default='http://localhost:8000')


# ========== JWT ==========
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
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
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
}

if not DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
        'rest_framework.renderers.JSONRenderer',
    ]
    logger.info("✅ DRF configured for production (JSON only)")


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
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'Lax'
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    logger.info("✅ Security middleware configured for production")


# ========== SOCIAL AUTH ==========
AUTHENTICATION_BACKENDS = (
    'social_core.backends.google.GoogleOAuth2',
    'django.contrib.auth.backends.ModelBackend',
)

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = config('SOCIAL_AUTH_GOOGLE_OAUTH2_KEY', default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = config('SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET', default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = ['email', 'profile']

if SOCIAL_AUTH_GOOGLE_OAUTH2_KEY and SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET:
    logger.info("✅ Google OAuth configured")
else:
    logger.warning("⚠️ Google OAuth credentials missing")


# ========== LOGGING ==========
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
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
            'level': 'WARNING',  # Set to INFO to see SQL queries in dev
        },
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

# ========== STARTUP MESSAGE ==========
logger.info("=" * 50)
logger.info("🚀 Hospital Backend Starting Up")
logger.info(f"🔧 DEBUG Mode: {DEBUG}")
logger.info(f"🌍 Allowed Hosts: {ALLOWED_HOSTS}")
logger.info(f"🗄️  Database: {DATABASES['default']['ENGINE']}")
logger.info(f"⚡ Redis Available: {bool(REDIS_URL)}")
logger.info(f"☁️  S3 Storage: {AWS_CREDENTIALS_PROVIDED}")
logger.info("=" * 50)